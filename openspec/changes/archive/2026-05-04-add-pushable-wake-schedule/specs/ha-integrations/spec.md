# ha-integrations Specification — delta

## ADDED Requirements

### Requirement: Operator-editable wake schedule

HA SHALL host an operator-editable wake-schedule definition at `ha/config/wake_schedule.yaml`. The file SHALL contain exactly four named tiers (`night`, `morning`, `midday`, `evening`) with `start` (HH:MM), `full_min`, `poll_min`, `partial_min` per tier, plus a `version` field at the top level. `partial_brings_poll` is NOT a field — it is derived by the firmware.

`ha/deploy.sh` SHALL deploy this file to the HAOS VM at `/config/custom/inkplate/config/wake_schedule.yaml`. The file lives next to the other operator-editable configs (`night_fallback_lines.yaml`, `poetic_weather_line.yaml`, etc.) and follows the same edit-and-redeploy workflow.

#### Scenario: Operator changes Midday cadence

- **WHEN** the operator edits `ha/config/wake_schedule.yaml` to change `midday.full_min` from 30 to 60 and runs `ha/deploy.sh`
- **THEN** the rendered YAML is rsync'd to `/config/custom/inkplate/config/`, HA reloads, the publish-wake-schedule automation fires on `homeassistant.start` (or its file-watch trigger), and the new JSON-form schedule is published retained to `inkplate/command/schedule`

### Requirement: Wake-schedule publisher automation

HA SHALL register an automation `inkplate_publish_wake_schedule` that:

- Triggers on `homeassistant.start`.
- Triggers on changes to `wake_schedule.yaml` (file-mtime change, or via a deploy-set `input_boolean.inkplate_wake_schedule_dirty` flag toggled by the deploy script after rsync).
- Reads the YAML file, validates it minimally (version present, four tiers present, `start` parseable), and renders to the canonical JSON shape per the device-wake-protocol spec.
- Publishes the JSON retained to `inkplate/command/schedule`.
- Logs the publish at `info` level so operators see it landed.

The automation SHALL be gated by `input_boolean.inkplate_publisher_enabled` (the master kill-switch, same as other publishers).

#### Scenario: HA-start publishes the current schedule

- **WHEN** HA boots fresh
- **THEN** within 10 s of `homeassistant.start`, the automation fires, reads the YAML, publishes the JSON retained to `inkplate/command/schedule`, ensuring the broker holds the operator's current schedule for any device wake that follows

#### Scenario: Master kill-switch

- **WHEN** the operator toggles `input_boolean.inkplate_publisher_enabled` to off and edits `wake_schedule.yaml`
- **THEN** the automation does not publish; the broker continues to hold whatever the previous publish was; the device runs on its cached schedule indefinitely

### Requirement: Minimal HA-side validation before publish

The publisher automation SHALL refuse to publish a YAML that fails any of these structural checks: missing `version`, missing tiers, tier count != 4, unknown tier name, unparseable `start`. On refusal it SHALL log a warning and leave the previously-published retained payload intact — so a typo'd YAML doesn't take the device off-cadence.

The full bounds + divisibility check is done device-side (per the device-firmware spec). HA validates only the structural shape; the device is the authority on numerical validity. This split keeps Jinja-template logic small and avoids duplicating the bounds rules in two places.

#### Scenario: Operator deploys YAML with missing tier

- **WHEN** the operator deploys `wake_schedule.yaml` with only three tiers (`night`, `morning`, `midday`) and no `evening`
- **THEN** the automation logs the refusal at `warning` level and does NOT publish; the retained `inkplate/command/schedule` topic remains unchanged; the device continues on its previously-cached schedule

### Requirement: Schedule-acknowledgement visibility

HA SHALL expose the device's currently-active schedule hash as `sensor.inkplate_device_schedule_hash`, sourced from the `schedule_hash` field of the retained `inkplate/state/device` JSON payload. The sensor's value MAY be displayed truncated, but the full 32-bit hex hash SHALL be available as the `hash_full` attribute.

The operator SHALL be able to compare this against the FNV-32 hash of the JSON HA most recently published. If they match, the device is running the operator's schedule. If they differ, the device hasn't yet picked up the new schedule (latest possible delay: one Full cycle, plus one wake to confirm via the next state/device publish).

The firmware therefore SHALL include the active `g_schedule_cache.payload_hash` in every state/device JSON publish under the key `schedule_hash`.

#### Scenario: Operator confirms the device picked up the new schedule

- **WHEN** the operator deploys a new `wake_schedule.yaml`, observes the publisher automation's log line confirming the publish, and then waits ≤ 30 min for a Full
- **THEN** the device's next state/device publish carries the new `schedule_hash`, HA's `sensor.inkplate_device_schedule_hash` updates to the new value, and the operator can verify it matches the hash of the just-published JSON