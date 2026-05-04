# device-firmware Specification — delta

## ADDED Requirements

### Requirement: Dynamic wake schedule resolution

The firmware SHALL resolve the wake schedule (tier boundaries and per-tier cadences for Full / Poll / Partial / PollPartial paths) from a layered set of sources, in priority order:

1. RTC slow memory cache (`g_schedule_cache`), populated by the most recent successful Full / Poll / PollPartial wake's MQTT read.
2. NVS-persisted schedule (namespace `"inkplate"`, key `"sched_v1"`), survives cold boot.
3. Baked default `kDefaultSchedule`, compiled into the firmware binary.

The firmware SHALL fall through to the next layer when the higher-priority layer is empty, has wrong version, or fails any structural / value validation.

`fw::wake::planWake()` SHALL accept the resolved `Schedule` as a parameter and use it instead of consulting any compile-time tier table. The pure-arithmetic algorithm of the planner (Full/Poll/Partial/PollPartial/Skip selection by minute-of-day modulo cadence) SHALL be preserved unchanged; only the data it reads is now dynamic.

#### Scenario: Steady-state wake reads cached schedule

- **WHEN** the device wakes from deep sleep with `Reason::Timer` and `g_schedule_cache.valid == 1`
- **THEN** `planWake()` is invoked with the cached `Schedule`, returns the path and minutes-to-next-wake derived from that schedule, and the wake proceeds without consulting NVS or the baked default

#### Scenario: Cold boot reads NVS

- **WHEN** the device cold-boots after a brown-out / watchdog / panic and RTC slow memory is wiped
- **THEN** the firmware reads the NVS blob `inkplate/sched_v1`, validates its `version` field against the firmware's supported version (1), populates `g_schedule_cache` from the NVS payload, and `planWake()` operates on that schedule for the cold-boot wake

#### Scenario: Cold boot with empty NVS falls back to baked default

- **WHEN** the device cold-boots after a fresh flash or NVS-erase, with no NVS blob present
- **THEN** the firmware uses `kDefaultSchedule`, `g_schedule_cache.valid` stays 0, and the cold-boot Full proceeds. On a subsequent Full's successful MQTT schedule read, `applySchedule()` writes both `g_schedule_cache` and the NVS blob.

#### Scenario: Schedule survives an unattended cold boot

- **WHEN** the operator has been running a custom schedule for two weeks, the device brown-outs at 03:00 (cold_boot from `ESP_RST_BROWNOUT`), and HA happens to be unreachable in the seconds following
- **THEN** the firmware reads the NVS blob, gets the operator's custom schedule, populates `g_schedule_cache`, and resumes on the custom cadence — without spending one wake on the baked default

### Requirement: Next-wake timing reflects updated schedule

When `applySchedule()` updates `g_schedule_cache` mid-tick, the wake-time computation for the very next deep sleep SHALL consult the updated cache. Specifically, `plannedSleepSec()` (called after `tick()` returns and before deep sleep) SHALL invoke `planWake()` against the freshly-resolved schedule, so a schedule update lands as soon as the wake that received it ends.

#### Scenario: Operator double-taps to apply a fresh schedule

- **WHEN** the operator publishes a new schedule (Midday `full_min: 60`) and double-taps the device
- **THEN** the IMU wake reaches `doFull`, fetches the new schedule, applies it to `g_schedule_cache`, and on return to `setup()` the next-sleep computation uses the new schedule — meaning the next Midday Full lands 60 minutes from now, not 30

### Requirement: Schedule payload validation

When the firmware fetches `inkplate/command/schedule` and the payload differs from the cached `payload_hash`, it SHALL parse and validate the JSON. The schedule SHALL be rejected (and the cached schedule preserved) on any of:

- `version != 1`.
- Tier count not exactly 4.
- Tier names not the canonical set `{night, morning, midday, evening}` (each present exactly once).
- Any tier with `full_min` outside `[1, 720]`.
- Any tier with `poll_min ≥ full_min` (when `poll_min > 0`).
- Any tier with `partial_min > full_min`.
- Any tier with `partial_min > 0` and `full_min % partial_min != 0`.
- Any tier with `poll_min > 0` and `full_min % poll_min != 0`.
- Any tier with `start_min % full_min != 0` (start must align to the Full cadence; a misaligned start would silently delay the first Full).
- Tier `start` times that do not have exactly four distinct values modulo 24 h.
- Malformed JSON, missing required fields, or unparseable HH:MM start times.
- Any numeric field that is negative, non-integer, or exceeds `INT16_MAX`.

Additional parser robustness contracts:

- The parser SHALL be **whitespace-tolerant**: `"key":1`, `"key": 1`, `"key" : 1`, and `"key"\n: 1` MUST all be accepted.
- The parser SHALL **scope per-tier field lookups** to the tier object's substring; finding `"full_min"` outside the current tier's `{...}` SHALL NOT be returned for that tier.
- The parser SHALL short-circuit on **empty payload** before hashing, parsing, or logging — an empty retained MQTT payload is "not yet published" and is NOT a parse failure.
- Integer parsing SHALL detect overflow; values outside `[INT16_MIN, INT16_MAX]` SHALL be rejected before bounds-check.

On rejection the firmware SHALL emit a `FW_LOG` line stating the specific violation so a bad operator edit shows up cleanly in serial output and the diag ring's "schedule_load_failed" flag bit.

#### Scenario: Bad payload preserves the working schedule

- **WHEN** an operator deploys a YAML with `morning.full_min: 0` and HA publishes the resulting JSON to `inkplate/command/schedule`
- **THEN** on the next Full wake the firmware fetches the payload, hashes it, sees the hash differs from cache, parses, detects `full_min == 0`, logs the rejection, leaves `g_schedule_cache` and NVS untouched, and continues running on the previous valid schedule. The next operator-published valid schedule replaces it normally.

#### Scenario: Pretty-printed JSON parses identically to compact JSON

- **WHEN** HA's publisher emits the schedule with default Jinja `tojson` formatting (single-line) AND when an operator manually publishes a multi-line, indented payload via `mosquitto_pub -m "$(cat schedule.json)"`
- **THEN** both payloads parse to the same `Schedule` and produce the same `payload_hash` (the hash is over the byte-identical raw payload, so different formatting will dedup-miss and re-parse — but both will parse successfully and produce the same operational schedule)

#### Scenario: Misaligned tier start is rejected

- **WHEN** an operator deploys `morning.start: "06:33"` with `morning.full_min: 15` (06:33 = 393 minutes; 393 % 15 = 3, not 0)
- **THEN** the firmware rejects the schedule, logs the misalignment, and the cached schedule is preserved

#### Scenario: Empty retained payload is silently ignored

- **WHEN** the device subscribes to `inkplate/command/schedule` for the first time and the broker has no retained value (returns empty string)
- **THEN** the firmware short-circuits before hashing or parsing, sets no diag flag, emits no log line — the empty case is "no schedule yet" and is not a parse failure

### Requirement: Hash-based dedup of schedule reads

To avoid re-parsing the schedule on every Full / Poll / PollPartial wake when nothing has changed, the firmware SHALL cache an FNV-32 hash of the JSON payload that produced the current `g_schedule_cache`. On each subsequent fetch, the firmware SHALL hash the new payload, and SHALL skip the parse + validation + cache write when the hash equals the cached value. The cache is updated only on hash mismatch.

#### Scenario: Unchanged schedule across many wakes

- **WHEN** the device wakes 100 times across a day and HA never republishes the schedule
- **THEN** each Full / Poll wake fetches the retained payload, computes its hash, finds it matches the cached hash, and skips re-parsing — saving ~50 µs per wake and avoiding any RTC / NVS writes

### Requirement: `partial_brings_poll` is derived, not stored

The firmware SHALL derive whether a tier's partials piggyback a poll round-trip from the rule `partial_brings_poll = (partial_min > 0 && poll_min == 0)`. This rule SHALL be evaluated at the use site in `pathForMinute()`; the flag SHALL NOT be a field in the JSON payload, the YAML, the `TierEntry` struct, or the NVS layout.

The rationale is that the explicit flag could disagree with the cadences (e.g., `poll_min: 5` and `partial_brings_poll: true` simultaneously) — making it derived eliminates that inconsistency.

#### Scenario: Midday tier piggybacks polls on partials

- **WHEN** a tier is configured with `full_min: 30, poll_min: 0, partial_min: 5`
- **THEN** `pathForMinute()` returns `Path::PollPartial` on minutes that are multiples of 5 (and not 30, which would be `Path::Full`), and `Path::Skip` on the other minutes within the tier — equivalent to today's hardcoded Midday behavior

#### Scenario: Tier with separate poll cadence does not piggyback

- **WHEN** a tier is configured with `full_min: 15, poll_min: 3, partial_min: 1`
- **THEN** `pathForMinute()` returns `Path::Full` on multiples of 15, `Path::Poll` on multiples of 3 that are not multiples of 15, `Path::Partial` on the other minutes — partials do NOT piggyback polls because `poll_min > 0`

### Requirement: state/device JSON carries `schedule_hash`

The `state/device` JSON payload SHALL include the field `"schedule_hash": "<8-hex-digit>"` carrying the lowercase hex of `g_schedule_cache.payload_hash`. When `g_schedule_cache.valid == 0` (running on baked default with no MQTT-derived schedule yet), the field SHALL be `"00000000"`.

This lets HA confirm the device is running the most recently-published schedule by matching this against the FNV-32 hash of the JSON HA last published. The visibility surface is one HA sensor (`sensor.inkplate_device_schedule_hash`) per the ha-integrations spec.

#### Scenario: Schedule update visible in next state/device publish

- **WHEN** HA publishes a new schedule JSON, the device's next Full reads it, parses, validates, and `applySchedule` updates `g_schedule_cache.payload_hash`
- **THEN** the same Full's state/device JSON publish carries the new `schedule_hash` value, HA's mirror sensor updates, and the operator can confirm the device adopted the change

### Requirement: Diag-ring flag bits for schedule events

The firmware SHALL extend `fw::diag::Entry::flags` with the following bit assignments:

- bit5 = `schedule_loaded_from_cache` — SHALL be set on every wake where `resolveSchedule()` returned the RTC cache (i.e., `g_schedule_cache.valid == 1`).
- bit6 = `schedule_loaded_from_nvs` — SHALL be set on the cold-boot wake where `resolveScheduleColdBoot()` returned a valid NVS-loaded schedule. SHALL be mutually exclusive with bit5 within a single tick.
- bit7 — SHALL remain reserved (no assignment in this change).

When a Full reads MQTT and `applySchedule()` replaces the cache (hash mismatch), the firmware SHALL NOT use a flag bit for that event — operators detect schedule-changed events via the `schedule_hash` field in state/device transitioning, which is more durable than a per-wake bit.

#### Scenario: Steady-state diag entries show cache-hit flag

- **WHEN** the device wakes 100 times across a steady-state day with a populated cache
- **THEN** all 100 diag entries have bit5 set; none have bit6 set; none have bit7 set