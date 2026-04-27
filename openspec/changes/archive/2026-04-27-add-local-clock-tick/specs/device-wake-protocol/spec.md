## MODIFIED Requirements

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
