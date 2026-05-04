# Design — Pushable wake schedule

## Storage layers

Three sources of schedule, consulted in this order:

1. **RTC slow memory** — `RTC_DATA_ATTR Schedule g_schedule_cache` (32 B
   tier table + 4 B JSON-payload hash + 1 B version + 1 B valid flag).
   Lives across deep sleep, wiped on cold boot. Read every wake.
2. **NVS (flash key-value)** — namespace `"inkplate"`, key
   `"sched_v1"`, blob == the binary form of the parsed `Schedule` struct.
   Survives cold boot. Read once on cold boot, written when (1) is updated.
3. **Baked default** — `constexpr Schedule kDefaultSchedule` in
   `firmware/src/wake.cpp`, identical to today's `tierFor()` table. Compiled
   into the firmware binary. Used when neither (1) nor (2) is valid.

Each layer is independently versioned; a layer with `version != 1` is
ignored as if absent. Mismatch → fall through to the next layer.

## Wake-time read flow

```
tick() entry
  ├── if wake reason in {Timer, IMU, HACommand, SonosFastPath, PostOTA}:
  │     → schedule = wake::resolveSchedule()
  │           ├── if g_schedule_cache.valid: use it
  │           ├── else: try NVS → on success, populate g_schedule_cache
  │           └── else: use kDefaultSchedule
  │
  ├── if wake reason == ColdBoot:
  │     → schedule = wake::resolveScheduleColdBoot()
  │           ├── try NVS → on success, populate g_schedule_cache
  │           └── else: use kDefaultSchedule
  │
  ├── planWake(local_min_of_day, mode, schedule) → path
  ├── ... existing logic, parameterized on `schedule` instead of `tierFor()` ...
  │
  └── on Full / Poll / PollPartial path with mqtt up:
        ├── payload = transport.mqttReadRetained("inkplate/command/schedule")
        ├── if payload empty: skip
        ├── new_hash = fnv32(payload)
        ├── if new_hash == g_schedule_cache.hash: skip (no change)
        ├── parsed = parseSchedule(payload)
        ├── if not parsed.valid: log diag flag, skip
        ├── g_schedule_cache = parsed; g_schedule_cache.hash = new_hash
        └── nvs_set_blob("sched_v1", &parsed, sizeof(parsed))
```

## On-the-wire payload

Topic: `inkplate/command/schedule`. Retained. JSON, single-document,
exactly four tiers. Validation rejects extra/missing tiers, names not in
the canonical four, fields out of bounds, non-divisible cadences, or
non-monotone tier starts.

```json
{
  "version": 1,
  "tiers": [
    {"name":"night",   "start":"22:00", "full_min":15, "poll_min":0, "partial_min":0},
    {"name":"morning", "start":"06:30", "full_min":15, "poll_min":3, "partial_min":1},
    {"name":"midday",  "start":"10:00", "full_min":30, "poll_min":0, "partial_min":5},
    {"name":"evening", "start":"17:00", "full_min":15, "poll_min":3, "partial_min":1}
  ]
}
```

Tiers are listed in chronological order across a 24-h day; "night"
straddles midnight and is identified by being the only tier with
`start ≥ next_tier.start`.

`partial_brings_poll` is **derived inside the firmware** at parse time as
`partial_min > 0 && poll_min == 0` — operators don't set it. This removes
a footgun where the explicit flag could disagree with the cadences. The
derivation matches today's hardcoded behavior bit-for-bit.

Time semantics: `start` strings are interpreted as **device-local wall
clock**, same as the existing `local_min_of_day` the planner already
uses. DST is out of scope (the firmware does not track DST transitions
and the operator is expected to re-deploy if DST shifts the schedule).

## RTC + NVS struct

```cpp
namespace fw::wake {

struct TierEntry {
  uint16_t start_min;        // minute-of-day, 0..1439
  uint16_t full_min;         // 1..720
  uint16_t poll_min;         // 0..(full_min-1); 0 = none
  uint16_t partial_min;      // 0..full_min; 0 = none
};
static_assert(sizeof(TierEntry) == 8, "TierEntry must be 8 bytes");

// `partial_brings_poll` is derived: `partial_min > 0 && poll_min == 0`.
// Computed at use-site in pathForMinute(); not stored.

struct Schedule {
  uint8_t  version;          // == 1 when valid
  uint8_t  valid;            // 0 = not yet populated; 1 = valid
  uint16_t pad;
  uint32_t payload_hash;     // FNV-32 of the JSON payload that produced this
  TierEntry tiers[4];        // ordered by entry across day (8 B × 4 = 32)
};
static_assert(sizeof(Schedule) == 40, "Schedule must be 40 bytes");

}  // namespace fw::wake
```

Total: 40 B in RTC slow memory; same 40 B written to NVS on update.

Tier names are advisory (only used in HA YAML as keys); firmware doesn't
store them — it just orders by `start_min`.

## JSON parser

Hand-rolled, fixed schema, no library. Cannot directly reuse the existing
`pickString` / `pickInt` from `main_loop.cpp` because they have two known
limitations that bite for nested-object JSON:

- `find("\"key\":\"")` is whitespace-intolerant — `"key": "value"` (the
  output of most JSON serialisers, including Jinja's `tojson`) silently
  fails to match. The schedule parser MUST be whitespace-tolerant.
- `pickInt(json, "full_min")` finds the FIRST occurrence in the entire
  document; with four tiers each having their own `full_min` it would
  return tier 0's value for all four tiers. The schedule parser MUST
  scope each tier-field lookup to that tier's substring.

```cpp
namespace fw::wake {

// Returns a Schedule with valid=1 on success. On any parse / validation
// failure, returns Schedule{} (valid=0) and logs the failure reason.
Schedule parseSchedule(const std::string& json);

// Helpers (in anonymous namespace inside wake.cpp):
//   - skipWs(const string&, size_t&) — advances past whitespace
//   - findKey(const string&, size_t scope_start, size_t scope_end,
//             const char* key) → position of value, or npos
//   - parseIntField(...) with bounds-check and overflow protection
//   - parseStringField(...) returning the unescaped string
//   - parseBoolField(...) — not used in v1 (`partial_brings_poll` derived)
//                           but useful if v2 adds boolean fields

}  // namespace fw::wake
```

Logic:
1. Find `"version":` integer (whitespace-tolerant); reject if not 1.
2. Find `"tiers":` then `[` (whitespace-tolerant); fail if not array.
3. Walk the array, identifying each of exactly 4 `{...}` tier objects by
   bracket-matching. Each tier object's substring becomes the *scope* for
   the per-field lookups below — keys are searched only within that
   scope.
4. For each tier:
   - Extract `name`, `start`, `full_min`, `poll_min`, `partial_min`.
   - Parse `start` as `HH:MM` (hour 0..23, minute 0..59) → `start_min`.
   - Bounds-check: `1 ≤ full_min ≤ 720`, `0 ≤ poll_min < full_min`,
     `0 ≤ partial_min ≤ full_min`. Reject negatives, > INT16_MAX, or
     non-numeric values.
   - Divisibility: if `partial_min > 0`, require `full_min % partial_min == 0`;
     if `poll_min > 0`, require `full_min % poll_min == 0`.
   - **Tier-start alignment**: require `start_min % full_min == 0`. A
     misaligned start would silently delay the first Full of the tier —
     reject up front rather than producing surprising cadence.
   - Tier name MUST be one of `{night, morning, midday, evening}`. Each
     name SHALL appear exactly once across the four tiers.
5. Sort the four tiers by `start_min`.
6. Verify all four `start_min` are distinct and span 24 h.
7. On any failure, return `Schedule{}` with the FW_LOG line stating the
   specific violation (so a bad YAML edit shows up cleanly in serial /
   the diag ring).

Estimated implementation: ~160 lines including helpers, scoped-search,
whitespace tolerance, and bounds-checks.

### Empty-payload short-circuit

Before hashing or parsing, the firmware SHALL check `if (payload.empty())
return;` — skipping both the dedup-hash check and the parse. Rationale:
the FNV-32 hash of `""` is non-zero, but `g_schedule_cache.payload_hash`
zero-initialises to 0; without the short-circuit, the first wake on a
broker that has never received a schedule publish would hash-mismatch,
attempt to parse an empty string, and emit a spurious "parse failed" diag
flag. The empty check turns "broker has nothing for us" into a no-op.

## Updated `planWake`

Today:
```cpp
WakePlan planWake(int local_min_of_day, fw::modes::Mode mode);
```

After:
```cpp
WakePlan planWake(int local_min_of_day, fw::modes::Mode mode,
                  const Schedule& schedule);
```

The `tierFor()` lookup becomes a linear scan over `schedule.tiers[4]`
finding which tier owns `local_min_of_day` (one tier wraps at midnight;
detected by `start_min` being numerically last but logically owning the
period from its start until tier 0's start the next day).

`pathForMinute()` body is unchanged — it just gets the chosen
`TierEntry` instead of the baked `Tier`. Same Path enum, same algorithm,
same exit conditions.

The "next non-Skip minute" search remains an O(1440) loop, identical to
today; just consults the dynamic table.

## Tap-driven sync

No code path is special-cased for taps. Every IMU wake takes the Full
path (existing behavior, unchanged). Every Full reads the retained
schedule topic. So a double-tap "synchronizing" the device is an
emergent property of the existing logic, not a new feature. This is
called out only because the operator may expect to see special handling
for it; there isn't any, and the design intentionally avoids adding it.

## NVS layout

```
namespace: "inkplate"
  key: "sched_v1"
    type: blob
    value: bytes 0..39 of `Schedule` struct (in-memory layout)
```

ESP32 NVS guarantees atomic blob writes (within a single sector). On
read, the firmware SHALL:

1. Verify the read returned exactly `sizeof(Schedule)` bytes. A
   smaller / larger blob means the firmware is reading a different
   schema's persistence (e.g., a future v2 layout) — reject and fall
   through to the next layer.
2. Verify the leading `version` byte == 1. Mismatch → reject.

Writes happen in `applySchedule(parsed)` in this strict order, all on
ARDUINO only:

```
nvs_set_blob("sched_v1", &parsed, sizeof(parsed));   // durable first
nvs_commit();                                          // flush to flash
g_schedule_cache = parsed;                             // RTC last
```

Rationale: NVS-then-RTC. A reset between the NVS write and the RTC write
loses RTC (wiped on cold boot anyway) but preserves the new schedule in
NVS — the next wake reads NVS, repopulates RTC, no schedule loss. The
reverse order would lose the just-applied change on a cold boot mid-update.

`nvs_set_blob` returning anything other than `ESP_OK` SHALL be logged
and SHALL NOT crash. RTC write proceeds anyway — the schedule remains
correct for the device's current uptime, only persistence is lost.
Cold-boot in that case falls back to the prior NVS blob (or baked
default if none).

## Validation strategy

The firmware test harness (`firmware/test/scenarios/`) gets:

1. `wake_schedule_parse_tests.cpp` — happy-path JSON, malformed JSON,
   each individual bounds violation, each divisibility violation, missing
   tier, extra tier, non-monotone starts, version != 1, empty payload,
   topic-not-set scenario. Asserts the right rejection reason.
2. `wake_schedule_plan_tests.cpp` — given a known `Schedule`, verify
   `planWake()` returns the same paths as today's hardcoded `tierFor()`
   for the default schedule. Plus a few alternative schedules (e.g.,
   morning Full=10, evening Full=20) to verify the dynamic dispatch.
3. `wake_schedule_persistence_tests.cpp` — host stub of NVS that the
   firmware can write/read; verifies cache → NVS → bake-default
   fallback chain.

Existing scenarios in `schedule_tests.cpp` are kept; they exercise the
default schedule and become regression coverage that the dynamic version
matches the baked behavior for the canonical input.

## Diag ring additions

Two new flag bits in `fw::diag::Entry::flags`:

- `bit5 = schedule_loaded_from_cache` (RTC hit)
- `bit6 = schedule_loaded_from_nvs` (NVS hit, RTC was empty)

(`bit7 = schedule_load_failed` is implied if neither cache nor NVS hit on
a wake that has mqtt up — operator can infer "running on baked default"
from the absence of both bits.)

When the schedule is updated mid-wake, the diag flag for that wake gets
both `schedule_loaded_from_cache` AND a new
`bit7 = schedule_updated_this_wake`. Operators reading the diag ring see
exactly when the device picked up a new schedule.

## What changes in HA

`ha/config/wake_schedule.yaml` — operator-editable, lives next to
`night_fallback_lines.yaml` and the other operator configs.

`ha/automations/publish_wake_schedule.yaml` — single automation, mirrors
the existing `publish_inputs.yaml` pattern:
- Trigger A: `homeassistant.start` (re-publish on every HA boot so the
  retained MQTT topic stays in sync after broker restarts).
- Trigger B: `event: state_changed` on a `binary_sensor` whose value is a
  template reading `wake_schedule.yaml`'s mtime — fires when the deploy
  script writes the file. (Alternative: a `command_line` sensor that
  hashes the file content; either is fine, no operator-visible
  difference.)
- Action: render the YAML to canonical JSON via Jinja, then
  `mqtt.publish` retained to `inkplate/command/schedule`. Gated by
  `input_boolean.inkplate_publisher_enabled` per the existing publisher
  convention.

## Risk: dynamic schedule diverging from the baked default

The baked default exists for cold-boot recovery. If the operator's
"normal" schedule diverges meaningfully from baked, every cold_boot
costs one wake on the wrong cadence. Mitigation: the NVS layer fixes
this — cold boot reads NVS, gets the operator's last-loved schedule
immediately. The baked default is only used when NVS is *also* empty,
which happens only on a fresh flash or a wiped NVS partition.

So the practical degradation path is:
- Cold boot from brown-out / panic → NVS cache used → operator's
  schedule preserved → no observable difference.
- Cold boot from flash erase → NVS empty → baked default used for one
  wake → next Full reads MQTT → operator's schedule restored.

## Out of scope

- Day-of-week variants — not in v1; would require expanding `Schedule`
  to a per-day-of-week array (7× 56 B = 392 B in RTC; doable but bigger).
- Per-mode tier overrides — Now-Playing's "every minute" is preserved
  as the existing hardcoded special case in `pathForMinute()`. A
  v1-schedule-aware operator can't override Now-Playing's cadence.
- Live mid-wake schedule updates — apply at start of next wake, not
  this one. Avoids races.
- Operator UI dashboard cards — Phase 1 is YAML edit + redeploy.
- Schema migration tooling — version 1 is the only schema until a v2
  proposal explicitly defines migration.
