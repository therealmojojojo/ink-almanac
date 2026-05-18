# Device firmware — spec delta

## ADDED Requirements

### Requirement: EPD clean-down probe

The firmware SHALL verify that the TPS65186 PMIC's power rails physically collapsed within a bounded timeout at the end of every Full wake, after the draw has completed and before the device-state JSON is published. The verification SHALL:

1. Call `IDisplay::ensurePanelDown(timeout_ms)` with `timeout_ms = 3000`.
2. The implementation SHALL invoke `panel_.einkOff()` (idempotent), then
   poll TPS65186 register 0x0F (PWR_GOOD) at 50 ms cadence over direct
   I²C until the byte reads `0x00` (all rails drained), `0xFF` (chip
   has stopped ACKing — also a valid terminal off-state on Inkplate 10
   where the chip's I²C goes quiet with WAKEUP low), or the timeout
   elapses.
3. The result (true = clean collapse, false = timeout with rails still
   partially asserted) SHALL be carried in the device-state JSON as
   `epd_down_clean: bool`.
4. The raw PWR_GOOD byte read at the end of the polling loop SHALL be
   carried in the device-state JSON as `epd_pg_raw: "0xNN"` (uppercase
   hex string).

A `false` return from `ensurePanelDown` is informational: it means the
current wake just *entered* the partial-power wedge state described in
`openspec/changes/prevent-tps65186-partial-power-wedge/proposal.md`,
and the *next* wake will probably find `ensurePanelPower` returning
false. The firmware SHALL NOT attempt further software recovery; the
existing diagnostic (`ensurePanelPower` on the next wake) and HA alert
path (`inkplate_epd_pwrgood_alert`) remain authoritative for actual
failures.

#### Scenario: Healthy chip collapses quickly

- **WHEN** a Full wake completes a draw at room temperature on a
  freshly-cold-booted chip
- **THEN** within 200 ms of `ensurePanelDown` being called, the polled
  PWR_GOOD reads 0x00 (or 0xFF, indicating chip is fully off and
  silent on I²C); the function returns true; the JSON carries
  `"epd_pg_raw": "0x00"` (or `"0xFF"`) and `"epd_down_clean": true`.

#### Scenario: Chip enters partial-power wedge

- **WHEN** a Full wake completes a draw but the rails do not collapse
  below the chip's PG threshold within the 3000 ms budget — instead
  staying at byte pattern 0xA0 (or similar non-zero, non-0xFF)
- **THEN** `ensurePanelDown` returns false; the JSON carries
  `"epd_pg_raw": "0xA0"` and `"epd_down_clean": false`; HA receives the
  payload and the predictive-warning automation fires on its
  debounce; the device sleeps anyway (no further action).

#### Scenario: I²C transient during polling

- **WHEN** an intermittent I²C bus glitch causes a single poll read to
  return 0xFF in the middle of an otherwise-healthy chip's rail
  collapse
- **THEN** the function treats 0xFF as "rails down" and returns true
  immediately; the JSON carries `"epd_down_clean": true`. (Acceptable:
  the chip would have reached 0x00 on the next poll anyway, and a
  one-poll-early "down" classification is harmless.)

### Requirement: PMIC raw byte in telemetry

The device-state JSON published on `inkplate/state/device` SHALL include
the raw PWR_GOOD byte (`epd_pg_raw`) alongside the existing
`epd_pwrgood` boolean. The raw byte SHALL be the value most recently
returned by `IDisplay::readPwrGoodByte()` at the end of the wake.

The two fields convey different information:
- `epd_pwrgood` (bool, existing): "did `ensurePanelPower()` succeed at
  the *start* of this wake?" — the exit check.
- `epd_pg_raw` (hex string, new): "what was the chip's actual rail
  state at the end of this wake?" — the entry check, plus the byte
  pattern needed to distinguish wedge type without USB.

#### Scenario: Wedge is diagnosable from telemetry alone

- **WHEN** the operator opens HA Developer Tools and inspects
  `sensor.inkplate_device_epd_pg_raw` after a panel-freeze incident
- **THEN** the value displayed is the byte pattern matching the failure
  class (e.g. `0xA0` for the partial-power wedge documented here),
  sufficient to identify the cause without flashing the USB diagnostic.
