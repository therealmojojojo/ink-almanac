# Push the wake schedule from HA instead of baking it in firmware

> **Status — 2026-05-03**: draft for discussion. No code yet.

## Why

The wake schedule — tier boundaries (Night / Morning / Midday / Evening), Full
cadence per tier, Poll cadence, Partial cadence, whether Partials piggyback
Polls — is hard-coded in `firmware/src/wake.cpp tierFor()`:

```cpp
constexpr Tier tierFor(int min_of_day) {
  if (min_of_day >= 1320 || min_of_day < 390) return {15, 0, 0, false};
  if (min_of_day < 600 || min_of_day >= 1020) return {15, 3, 1, false};
  return {30, 0, 5, true};
}
```

Every tweak — moving Morning's start from 06:30 to 07:00, dropping Midday's
partial cadence from 5 min to 10 min to save battery, changing Evening Poll
cadence — currently requires a USB cable, a `pio run --target upload`, a
cold-boot of the panel, and the operator standing at the device. That's a
30-second ritual per cadence change, plus the panel disruption. It also
discourages tuning: "is 5-min PollPartial the right Midday cadence?" is a
question we'd answer differently if iteration cost a redeploy instead of a
flash.

The active mode (which face to draw) is already operator-tunable from HA via
`inkplate/command/active_mode`. Extending the same pattern to the wake
schedule is a small, well-scoped change that decouples one whole class of
operational decision from firmware revisions.

## What Changes

### A. New retained MQTT topic — `inkplate/command/schedule`

JSON document, version-tagged:

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

Tiers are listed in the order they are entered during a day. Each tier owns
the time from its `start` until the next tier's `start` (modulo 24 h).
Exactly four tiers, names are advisory (used only in logs / diag).

The previous `partial_brings_poll` flag is **derived** by the firmware as
`poll_min == 0 && partial_min > 0` — the operator no longer sets it
explicitly. The rule says "if you have partials and no separate poll
cadence, partials piggyback a poll round-trip" which is exactly today's
Midday behavior; making this implicit removes a footgun (operators
setting an inconsistent flag) and tightens the schema.

### B. Firmware

- New `RTC_DATA_ATTR` struct alongside `Persisted`: a parsed `Schedule` (4
  tiers × 8 bytes = 32 B + 1-byte version + 1-byte valid flag).
- On every Full / Poll / PollPartial wake (i.e. wakes that already bring up
  WiFi+MQTT), the firmware reads `inkplate/command/schedule`, parses, validates,
  writes the parsed form to RTC. Cost: one extra MQTT round-trip on the same
  connection (≤50 ms typical).
- `wake::planWake()` consults the RTC cache. If empty / invalid / version
  mismatch → falls back to a baked-in default that matches today's behavior.
  No change in wake-time math beyond reading from a different source.
- Cold boot wipes RTC slow memory → first wake uses baked default → first Full
  re-populates the cache → subsequent wakes use the cache. No special code
  path for "first run."

### C. HA

A YAML file `ha/config/wake_schedule.yaml` operator-editable. An automation
publishes its rendered JSON to `inkplate/command/schedule` retained on:
- HA start.
- File change (deploy-driven; the deploy script triggers `homeassistant.reload`
  or similar).

Example file:
```yaml
# ha/config/wake_schedule.yaml — operator-editable wake schedule
version: 1
tiers:
  night:    {start: "22:00", full_min: 15, poll_min: 0, partial_min: 0}
  morning:  {start: "06:30", full_min: 15, poll_min: 3, partial_min: 1}
  midday:   {start: "10:00", full_min: 30, poll_min: 0, partial_min: 5}
  evening:  {start: "17:00", full_min: 15, poll_min: 3, partial_min: 1}
```

### D. Out of scope (explicit)

- **Day-of-week variants** (different schedule on weekends). Possible later;
  significantly more RTC space + parsing.
- **Per-mode overrides** (e.g., NowPlaying forces 1-min Fulls regardless of
  tier). Already exists today as a hardcoded special case in
  `pathForMinute()` — preserved unchanged in this change.
- **Operator UI dashboard cards.** YAML edit + redeploy is the Phase 1 UX.
- **Live mid-wake schedule reload.** Updates apply at the start of the next
  wake, not mid-tick. Avoids race conditions.
- **Schema migration.** Version 1 is the only schema; if/when a future change
  needs new fields, that's a separate openspec change with explicit migration
  rules.

## Why now

Every cadence question we've asked in the last two weeks ("is partial-1-min
right for Morning? would 2-min save battery?") has been parked because the
answer cost a flash. With this change, we test cadence changes by editing a
file and re-deploying HA. The diag-ring data this week will probably suggest
several cadence tweaks worth trying; this proposal makes those experiments
cheap.

## Risks

1. **Bricking on bad payload.** A malformed or hostile schedule could push the
   device into a tight loop (`full_min=0`) or near-permanent sleep
   (`full_min=1440`). Mitigated by strict bounds-check at parse time; reject
   the whole schedule and fall back to cache-or-baked-default. Bounds:
   `1 ≤ full_min ≤ 720`, `0 ≤ poll_min < full_min`, `0 ≤ partial_min ≤ full_min`,
   tier starts strictly increasing modulo 24h.
2. **First wake after cold-boot is on baked default.** If the operator has
   significantly diverged from the default (e.g., low-battery mode), they'll
   experience one wake on the old cadence after every cold-boot. Acceptable
   trade-off vs. complicating the cold-boot path.
3. **Test coverage.** The current `tierFor()` has doctest coverage for every
   boundary minute. The dynamic version needs equivalent coverage. Not free;
   not large either.
4. **Failure to read MQTT on a Full.** If MQTT is briefly unavailable, the
   cache stays as-is. That's fine — schedule changes are slow; one missed
   refresh is invisible. The cache only gets stale if HA goes away
   permanently, in which case the device runs on whatever cadence was live at
   HA's last publish.
