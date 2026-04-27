## ADDED Requirements

### Requirement: Wake-channel choice

The wake channel between HA and the device SHALL be one of:

- **MQTT**: HA publishes to a topic (e.g., `inkplate/wake`) with a small payload; the device subscribes when awake and acts immediately, or wakes via MQTT Last-Will or a GPIO-from-ESP32-co-processor hack when asleep (impractical for pure deep-sleep).
- **HTTP**: HA issues `POST /wake` to a small always-listening endpoint on the device; the device must have an always-listening surface, which conflicts with deep sleep.

Because an ESP32 in deep sleep cannot hold network state, neither pure MQTT nor pure HTTP works without adaptation. The practical choices are:

- **Option A — Polling wake via timer**: the device wakes on a short timer (e.g., every 5 minutes), queries HA for "should I be awake?", acts accordingly. Simple, but adds wake cost.
- **Option B — MQTT retained message + PIR-polling**: HA publishes a retained MQTT message with the current active mode; the device reads it on each wake. Still requires the device to wake for PIR/timer/IMU, but eliminates the need for a push channel.
- **Option C — Dedicated GPIO wake from a companion device**: an always-listening ESP8266/ESP32 co-processor translates MQTT messages into a GPIO pulse that wakes the Inkplate. Complex hardware addition.

The firmware SHALL adopt **Option B (MQTT retained message)** as the default. Option A is acceptable as a fallback during development. Option C is explicitly out of scope for this change.

#### Scenario: Wake signal via MQTT retained message

- **WHEN** HA wants to signal a wake (e.g., Now-Playing activates)
- **THEN** HA publishes a retained message to `inkplate/command/wake` with a small payload `{ at: <iso>, reason: "now_playing" }`, AND HA simultaneously publishes the active mode to `inkplate/command/active_mode`; the device reads both on its next natural wake (timer, PIR, or IMU)

### Requirement: Active-mode topic

HA SHALL maintain a retained MQTT topic `inkplate/command/active_mode` whose payload is the current active mode name. Updated whenever the active mode changes.

On each wake, the device SHALL subscribe to this topic, receive the retained message, and use it as the mode to fetch.

#### Scenario: Device wakes during Now-Playing

- **WHEN** the device wakes via PIR at 14:02 and music is playing
- **THEN** the retained topic holds `now-playing`, the device reads it, fetches `/display/now-playing.png`

### Requirement: Wake-reason topic

HA SHALL publish to `inkplate/command/wake_reason` a non-retained message whenever a high-priority wake is warranted (Now-Playing activation, track change, mode transition). The device, if awake, MAY act on this signal within the same cycle; if asleep, its next wake will observe the retained active_mode and proceed.

#### Scenario: Track change fires while device is awake

- **WHEN** the device is in the middle of a wake cycle and HA publishes to `wake_reason` due to a track change
- **THEN** the device re-fetches the mode's PNG before re-entering deep sleep, so the freshest content is displayed

### Requirement: Device-state topic

The device SHALL publish to `inkplate/state/device` a non-retained message at the end of each wake cycle containing:

- battery_voltage
- battery_percentage
- last_wake_reason
- last_mode_drawn
- firmware_version
- wake_count_since_boot

This topic is consumed by HA for low-battery notifications and diagnostics.

#### Scenario: Battery report appears in HA

- **WHEN** the device publishes to `inkplate/state/device` with `battery_percentage: 18`
- **THEN** HA's template sensor updates to 18%, the low-battery threshold trigger fires, and a notification is sent

### Requirement: MQTT broker

HA SHALL run the Mosquitto MQTT broker (via the MQTT add-on) on the HAOS VM, reachable from the device on the LAN. Credentials SHALL live in the device's `secrets.h` and on HA.

The device SHALL use QoS 0 for most messages (state, reason) and QoS 1 only for wake commands if the project decides to push-via-GPIO later (currently not the case).

#### Scenario: Broker running at boot

- **WHEN** the device boots and connects to WiFi
- **THEN** it can connect to the MQTT broker at the configured host within 5 seconds

### Requirement: Connection loss handling

The device SHALL remain functional when MQTT connectivity is lost.

When the device fails to connect to the MQTT broker or the broker is unreachable:

- The device SHALL still wake on its local triggers (timer, PIR, IMU INT).
- The device SHALL fall back to time-of-day mode inference (per the renderer-unreachable fallback rule in `device-firmware`).
- The device SHALL retry MQTT on each wake with exponential backoff (30s, 1min, 5min, capped at 5min).

#### Scenario: Broker offline for 30 minutes

- **WHEN** the MQTT broker is offline and the device wakes multiple times
- **THEN** each wake falls back to local schedule inference, fetches the corresponding mode PNG, and re-attempts MQTT before sleep
