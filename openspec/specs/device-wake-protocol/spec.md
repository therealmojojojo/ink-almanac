# device-wake-protocol Specification

## Purpose
TBD - created by archiving change add-device-firmware. Update Purpose after archive.
## Requirements
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

The device SHALL publish to `inkplate/state/device` a retained message at the end of each **full-cycle** wake containing:

- `battery_voltage`
- `battery_percentage`
- `wake_reason` (one of `cold_boot`, `post_ota`, `timer`, `local_tick`, `imu`, `ha_command`, `sonos_fast_path`)
- `active_mode`
- `build` (firmware version)
- `rtc_source` — `"external"` when PCF85063A is reachable, `"internal"` on fallback
- `zones_version` — sha256 hash of the cached zones.json snapshot, or `null` if unavailable

`LocalTick` wakes SHALL NOT publish to this topic. At ~930 LocalTick wakes/day, publishing each would produce HA-side noise without informational value — battery and other state drift slowly enough that the full-cycle cadence (≥ every 60 min, typically every 15 min) is sufficient for HA's downstream consumers.

If a LocalTick wake is promoted to a full-cycle refresh (ghost-clear boundary hit), the promoted cycle publishes `state/device` as usual, with `wake_reason: local_tick` to make the promotion visible in diagnostics.

This topic is consumed by HA for low-battery notifications, diagnostics, and the `sensor.inkplate_device_*` template sensors.

#### Scenario: Battery report after full-fetch wake

- **WHEN** the device wakes at 14:15 with `Reason::Timer` for a scheduled full fetch and reads 3.78 V battery
- **THEN** the device publishes approximately `{ voltage: 3.78, percentage: 62, wake_reason: "timer", active_mode: "gallery", build: "...", rtc_source: "external", zones_version: "sha256:..." }` to `inkplate/state/device`

#### Scenario: LocalTick wake does not publish

- **WHEN** the device wakes at 14:17 with `Reason::LocalTick`, draws the clock locally, and returns to sleep
- **THEN** no MQTT connection is established and no `state/device` message is published; HA's view of device state remains the last full-cycle snapshot

#### Scenario: Ghost-clear promotion publishes with LocalTick reason

- **WHEN** a LocalTick wake is promoted to a full-cycle refresh because `partial_refresh_count` reached 30
- **THEN** the promoted cycle publishes `state/device` with `wake_reason: "local_tick"`, making the ghost-clear promotion visible in HA logs without introducing a new wake-reason token

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

There is no `partial_brings_poll` field — partials are always offline
(no WiFi, no MQTT). An operator who wants MQTT-based mode-change pickup
between Fulls SHALL declare a positive `poll_min` in the tier; the
firmware no longer auto-folds a poll into a partial when `poll_min == 0`.

The topic SHALL be retained so the device, on every wake's MQTT subscribe, immediately receives the current authoritative schedule from the broker without timing coordination.

The four tier names form the canonical set; their order in the JSON array MAY be any but the firmware SHALL sort by `start_min` after parsing.

#### Scenario: Schedule published once on HA start

- **WHEN** Home Assistant boots and the operator-edited `ha/config/wake_schedule.yaml` is loaded
- **THEN** the publish-wake-schedule automation fires on `homeassistant.start`, renders the YAML to the canonical JSON shape, and publishes retained to `inkplate/command/schedule` — making the latest schedule available to the device's next wake

#### Scenario: Operator edits schedule mid-day

- **WHEN** the operator edits `wake_schedule.yaml` to lower Midday `full_min` from 30 to 60, runs `ha/deploy.sh`, and the deploy triggers HA's reload
- **THEN** HA publishes the new JSON retained to `inkplate/command/schedule`, the broker stores it as the latest retained value, and the device picks it up on its next Full / Poll wake (within ≤ 30 min in the worst case, immediately if the operator double-taps)

### Requirement: Schedule retained-payload contract

The retained payload SHALL always represent a complete, valid schedule. Partial / patched payloads (e.g., updating just one tier's `full_min`) are NOT supported in v1. HA SHALL re-render the entire schedule on every publish.

The empty-string payload SHALL be treated by the firmware as "no schedule published" (use cached or baked default). HA SHALL NOT publish an empty payload as a way to "reset" the schedule; resetting is operator-side by editing the YAML to the default values and republishing.

#### Scenario: Empty retained payload

- **WHEN** HA's broker has never received a schedule publish for this topic and the device subscribes for the first time
- **THEN** the broker delivers no message (no retained value), the device's `mqttReadRetained` returns empty, and the firmware uses its cached or baked-default schedule unchanged

