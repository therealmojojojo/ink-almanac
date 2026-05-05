# device-firmware Specification — delta

## ADDED Requirements

### Requirement: Panel power-good diagnostic in device-state

The firmware SHALL probe the EPD PMIC's power-good status before each full-cycle draw and SHALL include the result as a boolean field `epd_pwrgood` in the JSON published to retained MQTT `inkplate/state/device`.

The probe SHALL be performed via the HAL method `IDisplay::ensurePanelPower()`. Real hardware implementations (`RealDisplay`) SHALL delegate to the Soldered library's `Inkplate::einkOn()` and report whether `readPowerGood()` reached `PWR_GOOD_OK` within the library's timeout. Host-simulator implementations MAY return `true` unconditionally.

When the probe returns `false`, the firmware SHALL NOT attempt the renderer fetch or the panel draw for that wake (the Soldered library would silently bail internally; skipping saves the network round-trip and the wake-time budget). The firmware SHALL still publish `state/device` with `epd_pwrgood: false` so the failure is observable from HA.

The firmware MAY skip the diagnostic on partial-only wakes (the 1-min clock tick); detection on full-cycle wakes is sufficient given the ≤30-minute Full cadence.

#### Scenario: Healthy wake

- **WHEN** the device wakes for a Full and the EPD PMIC powers up successfully
- **THEN** the device fetches and draws normally and publishes `"epd_pwrgood": true` in the `state/device` payload

#### Scenario: PMIC fault during wake

- **WHEN** the device wakes for a Full and `einkOn()` returns 0 because the TPS65186 fault-latched (failed to assert `PWR_GOOD_OK` within the library's 250 ms timeout)
- **THEN** the device skips the renderer fetch and the panel draw, and publishes `"epd_pwrgood": false` in the `state/device` payload along with the rest of the standard fields (battery, voltage, wake_reason, active_mode, build)

#### Scenario: Recovery on next wake

- **WHEN** a previous wake published `epd_pwrgood: false` and the next wake's `einkOn()` succeeds
- **THEN** the device draws normally and publishes `epd_pwrgood: true`; HA observes the binary-sensor transition without operator intervention being required for self-resolving transients
