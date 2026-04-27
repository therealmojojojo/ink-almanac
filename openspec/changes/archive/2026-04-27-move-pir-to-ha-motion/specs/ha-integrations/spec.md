## ADDED Requirements

### Requirement: Kitchen-motion wake automation

HA SHALL integrate a standalone battery-powered kitchen motion sensor. The reference implementation uses an IKEA TRADFRI motion sensor paired via the zigbee2mqtt bridge running on the NUC (ConBee II coordinator); MQTT autodiscovery surfaces it in HA as `binary_sensor.kitchen_motion_sensor_occupancy`. Any equivalent `binary_sensor` may be substituted — the automation references entity IDs, not the specific integration.

HA SHALL run an automation that translates motion into a device-wake pulse under the following conditions:

- **Trigger**: `binary_sensor.kitchen_motion_sensor_occupancy` transitions `off → on`.
- **Conditions (all must hold)**:
  - Current time is **not** within the quiet-hours window defined by `input_datetime.inkplate_quiet_start` / `inkplate_quiet_end` (default 00:00–05:00), handling midnight wrap correctly.
  - `input_text.inkplate_active_override` equals `schedule` — motion SHALL NOT preempt an active higher-precedence override (`now_playing`, `weather_peek`, `summary_gallery_toggle`).
- **Throttle**: the automation SHALL NOT fire more than once per 5 minutes (same semantic as the former on-device PIR cooldown).
- **Action**: publish an empty payload to `inkplate/command/wake` (retained=false).

The device-side behavior is defined by `device-firmware` Sleep strategy: the wake pulse is observed on the device's next natural wake (timer or Sonos fast-path). HA SHALL NOT attempt to deliver the pulse with lower latency than the MQTT retained-message mechanism allows.

#### Scenario: Motion during Summary hours

- **WHEN** it is 08:45 (Summary hours, no override active) and the kitchen motion sensor transitions to `on`
- **THEN** HA's `kitchen_motion_wake` automation fires, publishes to `inkplate/command/wake`, and does not fire again until at least 08:50

#### Scenario: Motion during quiet hours

- **WHEN** it is 02:30 and the kitchen motion sensor transitions to `on`
- **THEN** the automation SHALL NOT publish to `inkplate/command/wake`; Night mode continues its 60-min timer cadence uninterrupted

#### Scenario: Motion during Now-Playing

- **WHEN** music is playing (active override = `now_playing`) and the kitchen motion sensor transitions to `on`
- **THEN** the automation SHALL NOT publish to `inkplate/command/wake`; Now-Playing continues without an extra refresh

#### Scenario: Motion-wake storm throttled

- **WHEN** the kitchen motion sensor fires three times in 90 seconds during an eligible window
- **THEN** only the first trigger publishes to `inkplate/command/wake`; the second and third are suppressed by the 5-min throttle

#### Scenario: Motion pulse observed on fast-path wake

- **WHEN** HA publishes `inkplate/command/wake` at 14:20:05, the device is in Gallery mode in deep sleep, and the Sonos fast-path timer is set for 14:23:00
- **THEN** the device wakes at 14:23:00 with `Reason::SonosFastPath`, reads retained `active_mode`, and refreshes accordingly

### Requirement: Motion sensor low-battery notification

HA SHALL monitor the kitchen motion sensor's battery entity (`sensor.kitchen_motion_sensor_battery` under the reference zigbee2mqtt implementation) and send a notification to the operator's phone when the battery reports below 20%. Re-notification SHALL throttle — no more than one notification per 24 hours for the same threshold crossing. Rationale: coin-cell batteries drain over months; a 4-hour throttle (as used for the device's LiPo) would over-notify.

#### Scenario: Motion-sensor battery dips below 20%

- **WHEN** `sensor.kitchen_motion_sensor_battery` reports 18
- **THEN** an HA notification is sent to the operator's phone within 2 minutes, and no additional notifications for this crossing are sent for 24 hours
