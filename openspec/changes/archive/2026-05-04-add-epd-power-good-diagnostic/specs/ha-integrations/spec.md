# ha-integrations Specification — delta

## ADDED Requirements

### Requirement: EPD power-good binary sensor and alert

HA SHALL expose `binary_sensor.inkplate_device_epd_power_good` reading the `epd_pwrgood` boolean from retained `inkplate/state/device`. The sensor SHALL use `device_class: problem` (so the `on` state means "wedged" / problem present, matching HA UX conventions).

HA SHALL register an automation that, when the binary sensor stays in the problem state for at least one full-cycle window (default `for: "00:31:00"` to cover the slowest Midday cadence), notifies the operator via `notify.inkplate_operator`. The notification SHALL state that the panel is wedged, that recovery requires removing the LiPo battery, and SHALL include the most recent battery percentage and wake_reason for context.

The automation SHALL apply a 4-hour re-notification throttle (matching `inkplate_low_battery_notify`) so a sustained outage does not produce a steady stream of identical alerts.

#### Scenario: Wedge detected and notified

- **WHEN** the device publishes `epd_pwrgood: false` on two consecutive full-cycle wakes (≥ 31 minutes apart in Midday)
- **THEN** HA emits a single `notify.inkplate_operator` notification stating the panel is wedged and prompting battery removal

#### Scenario: Transient PMIC fault not notified

- **WHEN** a single wake publishes `epd_pwrgood: false` but the next wake publishes `true`
- **THEN** the binary sensor flips on then off without exceeding the `for:` debounce window, and no notification is emitted

#### Scenario: Sustained wedge does not spam

- **WHEN** the panel stays wedged across a 12-hour window (the device keeps publishing `false` every 15-30 min)
- **THEN** the operator receives at most one notification every 4 hours
