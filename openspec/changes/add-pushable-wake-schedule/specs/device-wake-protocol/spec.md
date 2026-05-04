# device-wake-protocol Specification — delta

## ADDED Requirements

### Requirement: Wake-schedule MQTT topic

HA SHALL publish the device's wake schedule to the retained MQTT topic `inkplate/command/schedule`. The payload SHALL be a single JSON document conforming to the schedule schema (version 1):

```json
{
  "version": 1,
  "tiers": [
    {"name":"<night|morning|midday|evening>",
     "start":"HH:MM",
     "full_min":<int>,
     "poll_min":<int>,
     "partial_min":<int>},
    ... exactly 4 tiers ...
  ]
}
```

`partial_brings_poll` is derived by the firmware at parse time as
`partial_min > 0 && poll_min == 0` and SHALL NOT appear in the JSON payload.

The topic SHALL be retained so the device, on every wake's MQTT subscribe, immediately receives the current authoritative schedule from the broker without timing coordination.

The four tier names form the canonical set; their order in the JSON array MAY be any but the firmware SHALL sort by `start_min` after parsing.

#### Scenario: Schedule published once on HA start

- **WHEN** Home Assistant boots and the operator-edited `ha/config/wake_schedule.yaml` is loaded
- **THEN** the publish-wake-schedule automation fires on `homeassistant.start`, renders the YAML to the canonical JSON shape, and publishes retained to `inkplate/command/schedule` — making the latest schedule available to the device's next wake

#### Scenario: Operator edits schedule mid-day

- **WHEN** the operator edits `wake_schedule.yaml` to lower Midday `full_min` from 30 to 60, runs `ha/deploy.sh`, and the deploy triggers HA's reload
- **THEN** HA publishes the new JSON retained to `inkplate/command/schedule`, the broker stores it as the latest retained value, and the device picks it up on its next Full / Poll / PollPartial wake (within ≤ 30 min in the worst case, immediately if the operator double-taps)

### Requirement: Schedule retained-payload contract

The retained payload SHALL always represent a complete, valid schedule. Partial / patched payloads (e.g., updating just one tier's `full_min`) are NOT supported in v1. HA SHALL re-render the entire schedule on every publish.

The empty-string payload SHALL be treated by the firmware as "no schedule published" (use cached or baked default). HA SHALL NOT publish an empty payload as a way to "reset" the schedule; resetting is operator-side by editing the YAML to the default values and republishing.

#### Scenario: Empty retained payload

- **WHEN** HA's broker has never received a schedule publish for this topic and the device subscribes for the first time
- **THEN** the broker delivers no message (no retained value), the device's `mqttReadRetained` returns empty, and the firmware uses its cached or baked-default schedule unchanged