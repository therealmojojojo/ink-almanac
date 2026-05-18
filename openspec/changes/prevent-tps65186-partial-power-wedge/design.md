# Design — prevent-tps65186-partial-power-wedge

## Failure mode (confirmed empirically on 2026-05-17)

The Soldered library's `TPS65186::powerDown()`, called by `einkOff()`
at the end of every `display()` / `partialUpdate()`:

```cpp
void TPS65186::powerDown() {
  _expander->digitalWrite(_vcomPin,  LOW, true);
  _expander->digitalWrite(_pwrupPin, LOW, true);
  unsigned long timer = millis();
  do { delay(1); }
  while ((readPowerGood() != 0) && (millis() - timer) < 250);
  _expander->digitalWrite(_wakeupPin, LOW, true);
  enableRails(false);   // return code discarded
  _poweredUp = false;
}
```

Hard 250 ms cap on the rail-collapse wait. If rails haven't drained
below PG threshold in 250 ms — which happens when caps hold longer than
expected after a warm 3-bit full draw — the library forces
`enableRails(false)` over I²C anyway. The chip's enable bit goes to 0;
the physical rails do not. On the next wake, `einkOn()` calls
`powerUp()` which polls `readPowerGood() == 0xFA` (all rails good)
with a 250 ms timeout; the chip's sequencer sees the partial-up state
and refuses to drive new rails, so `0xFA` is never reached and
`einkOn()` returns 0. Every subsequent draw call is a silent no-op.

## Solution shape

Wrap the library's `einkOff()` at the HAL boundary (not inside
Soldered's code — keep them upstream) so the firmware:

1. Calls `panel_.einkOff()` (idempotent; runs the library's full
   power-down sequence including its own 250 ms wait).
2. Polls TPS65186 register 0x0F directly until it reads 0x00 (all
   rails drained) or 0xFF (chip stopped ACKing, which is also "off").
3. Has up to 3000 ms total budget. On a healthy chip the rails reach
   0 within ~100 ms after step 1; the budget exists for the marginal
   cases where caps need longer.

If the budget is exhausted with the chip still reporting partial rails,
the firmware records that fact (`epd_down_clean = false`) and includes
the raw PWR_GOOD byte in telemetry. The wake completes normally — we
do not retry indefinitely, because if 3 s wasn't enough, more I²C
writes won't help. But HA now has a *predictive* signal: the next
wake will probably enter the wedge.

## Why polling and not interrupt-driven

The TPS65186 doesn't have a "rails-collapsed" interrupt pin wired to
the ESP32 on Inkplate 10. The MCP23017 expander's INTA/INTB lines are
used for the touch buttons. Polling is the only mechanism.

## Why 3 seconds

Picked empirically:

- Library's own wait is 250 ms.
- Healthy chip collapses to `0x00` in ~100 ms after the library
  finishes (caps discharging through the panel's static load).
- 1 s headroom would catch most marginal cases.
- 3 s gives generous headroom for cold environments where caps hold
  longer, with negligible cost on a 15-minute cadence (1 part in 300).

If telemetry shows wake durations creeping above 1 s consistently, we
should investigate; it would indicate the chip is taking the full
budget every time, which means we're near the wedge boundary on every
wake.

## I²C read semantics

On a healthy off chip, WAKEUP is low and the chip's I²C interface
typically does not ACK. Our diagnostic confirmed both behaviors are
possible depending on chip state — `readPwrGoodByte()` returns 0xFF on
a NACK. We treat 0xFF as "off" in `ensurePanelDown` because:

- The wedged state always ACKs and returns a non-zero byte (we saw
  0xA0 across all four diagnostic stages with WAKEUP eventually low).
- A clean off chip may or may not ACK; if it doesn't, that's still the
  desired terminal state.

The distinction *between* 0xFF and 0x00 doesn't matter for the
ensurePanelDown decision but DOES matter for telemetry — we publish
the raw byte so HA can see "0xFF (chip silent)" vs "0xA0 (wedged)"
vs "0xFA (still on??)" directly.

## What does NOT change

- The `einkOn`/`ensurePanelPower` probe (added in
  `add-epd-power-good-diagnostic`) stays as-is. It catches *exit*
  failures (chip already wedged when this wake started). The new
  `ensurePanelDown` catches *entry* failures (chip about to wedge as
  this wake ends).
- The existing `binary_sensor.inkplate_device_epd_power_good`,
  `inkplate_epd_pwrgood_alert` automation, and operator notification
  channel are reused. We add new entities and a parallel earlier-warning
  alert alongside them, not replacing.
- The MQTT topic `inkplate/state/device` keeps its retained semantics
  and JSON shape (additive — new fields, no removed ones).

## Defaults for non-Real targets

`IDisplay::ensurePanelDown()` and `IDisplay::readPwrGoodByte()` default
to `true` and `0xFA` respectively. MockDisplay inherits these defaults,
so all existing scenario tests pass unchanged. Tests that want to
simulate the wedge can override via subclass or scenario-level setters
in a future iteration; not needed for this change because the wedge is
a hardware-level phenomenon we can't reproduce in software anyway.
