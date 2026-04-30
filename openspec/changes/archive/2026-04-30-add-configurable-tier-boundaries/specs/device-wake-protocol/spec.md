# device-wake-protocol — delta

## ADDED Requirements

### Requirement: Tier-boundary topic

HA SHALL maintain a retained MQTT topic `inkplate/command/tier_boundaries` whose payload is a JSON object declaring the start time of each schedule tier as `HH:MM` local-time strings:

```json
{
  "morning_start": "06:30",
  "midday_start":  "10:00",
  "evening_start": "17:00",
  "night_start":   "22:00"
}
```

The payload SHALL satisfy:

1. All four fields present and parseable as `HH:MM`.
2. Strictly increasing in clock-time order: `morning_start < midday_start < evening_start < night_start`.
3. Each tier ≥ 30 minutes wide.

The Night tier wraps midnight by construction (from `night_start` to `morning_start` of the next day) and is not encoded explicitly.

#### Scenario: Device reads tier boundaries on wake

- **GIVEN** the broker holds the retained payload above
- **WHEN** the device wakes for any reason
- **THEN** the device reads the topic, validates the payload, and stores the four minute-of-day integers in its `Persisted` RTC RAM

#### Scenario: Topic absent on the broker

- **GIVEN** no payload is retained on `inkplate/command/tier_boundaries`
- **WHEN** the device wakes
- **THEN** the device's cached values are not modified, AND the schedule planner uses whatever values are already cached (or compile-time defaults if the cache is empty)

### Requirement: Tier-boundary fallback semantics

The firmware SHALL fall back to compile-time default boundaries (Morning 06:30, Midday 10:00, Evening 17:00, Night 22:00) when:

- The RTC cache has never been populated (cold boot, first wake)
- The most recent payload failed parse or validation
- The broker is unreachable on the wake that needed the values

The fallback values SHALL match the behavior shipped before this change so a device that never sees the new topic operates identically to today.

#### Scenario: Cold boot before first MQTT read

- **GIVEN** a device boots with `Persisted::morning_start_min == 0` (zero-sentinel)
- **WHEN** `wake::tierFor(min_of_day)` is called before any MQTT read completes
- **THEN** the planner uses `kDefaultBoundaries` and classifies minutes as it does today

#### Scenario: Malformed payload received

- **GIVEN** the broker holds a payload that fails parse or validation (missing field, non-monotone, tier <30 min)
- **WHEN** the device reads the topic
- **THEN** the cached RTC values are NOT overwritten, AND a log line records the failure with the offending payload abbreviated, AND the planner continues using whatever values were valid last (cached or default)

### Requirement: Per-tier cadences remain compile-time

Per-tier cadence parameters (`full_min`, `poll_min`, `partial_min`, `partial_brings_poll`) SHALL remain compile-time constants in `firmware/src/wake.cpp`. Only the four tier boundaries are runtime-configurable.

Rationale: cadences are tied to hardware behavior (panel refresh time ~3 s, partial-pulse cost ~0.06 mAh, post-Full clock cleanup timing) and to the partial-update path's correctness invariants. Changing them at runtime adds risk for a knob no operator is asking to turn.

#### Scenario: Operator wants different Midday cadence

- **GIVEN** an operator wants Midday's Full cadence to be 20 minutes instead of 30
- **WHEN** they look for a way to change it
- **THEN** the answer is a firmware change to `wake.cpp::tierFor()` and a separate openspec change, not an HA helper
