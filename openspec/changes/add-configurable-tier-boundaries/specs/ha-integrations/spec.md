# ha-integrations — delta

## ADDED Requirements

### Requirement: Tier-boundary helpers

`ha/integrations/helpers.yaml` SHALL declare four `input_datetime` helpers, time-only, with the following names and defaults:

| Helper | Default |
| --- | --- |
| `inkplate_morning_start` | `06:30` |
| `inkplate_midday_start` | `10:00` |
| `inkplate_evening_start` | `17:00` |
| `inkplate_night_start` | `22:00` |

Defaults match the values shipped before this change so a fresh installation reproduces today's schedule.

#### Scenario: Operator views the helpers in HA UI

- **GIVEN** a fresh installation with this change deployed
- **WHEN** the operator opens HA's Helpers settings
- **THEN** the four `input_datetime` cards are visible with the defaults above

### Requirement: Tier-boundary publisher automation

HA SHALL publish a retained payload to `inkplate/command/tier_boundaries` whenever any of the four helpers changes state, AND on `homeassistant.start` (defensive against broker restarts losing the retained message).

The publisher SHALL run a Jinja validator template before each publish. The validator SHALL fail when:

- Any helper has not been initialized (state is `unknown` or `unavailable`)
- The four helpers do not satisfy `morning_start < midday_start < evening_start < night_start`
- Any tier (the gap between consecutive boundaries) is less than 30 minutes

On validation failure the publisher SHALL refuse to publish; the previously valid retained payload remains on the broker; a warning is logged to the HA system log; an operator notification is fired through the existing notify channel used by `low_battery.yaml`.

#### Scenario: Operator shifts Morning start to 07:00

- **GIVEN** the four helpers hold their defaults
- **WHEN** the operator changes `inkplate_morning_start` to `07:00`
- **THEN** the validator passes (still monotone, all tiers ≥ 30 min wide), AND the publisher fires, AND the retained payload at `inkplate/command/tier_boundaries` reflects the new Morning start within seconds

#### Scenario: Operator inverts Morning and Midday

- **GIVEN** the operator sets `inkplate_morning_start` to `12:00` (past `inkplate_midday_start = 10:00`)
- **WHEN** the publisher fires
- **THEN** the validator fails (non-monotone), AND no MQTT publish happens, AND the previous valid retained payload remains, AND a warning appears in the HA log

#### Scenario: HA restart with valid retained payload

- **GIVEN** a valid retained payload exists on the broker
- **WHEN** HA restarts
- **THEN** on `homeassistant.start` the publisher republishes the payload built from current helper states, idempotent (same payload as before)

#### Scenario: First install with no retained payload

- **GIVEN** a fresh broker with no `inkplate/command/tier_boundaries` retained
- **WHEN** HA starts and helpers are at defaults
- **THEN** the publisher publishes the defaults so a device that wakes immediately reads a valid payload

### Requirement: Schedule consumers source from helpers

`ha/automations/schedule.yaml` and `ha/automations/gesture_override.yaml` SHALL compute tier boundaries from the four `input_datetime.inkplate_*_start` helpers, not from inline literals.

This is the operative deduplication the change exists to deliver: a single source of truth for boundaries on the operator-facing edit surface.

#### Scenario: Operator shifts Midday start to 11:00 mid-day

- **GIVEN** the device is currently in Midday with Gallery shown
- **WHEN** the operator changes `inkplate_midday_start` from `10:00` to `11:00` at 10:30 local time
- **THEN** the publisher republishes the retained payload, AND the next alternation tick (within 15 min) computes `tier == Morning` for the current minute, AND the next firmware wake reads the new boundaries from the retained topic and applies them on subsequent `tierFor` calls
