# Surface EPD power-good as a device-state diagnostic

> **Status — 2026-05-01**: proposed; firmware + HA wiring drafted.

## Why

On 2026-04-30 the panel froze on a stale gallery face for ~10 h before
the operator noticed. The ESP32 was healthy throughout — wakes happened
on schedule, MQTT publishes landed in HA every 15 min, taps were detected
and forwarded as gestures. Yet **no panel update happened from 21:52
yesterday through 07:48 this morning**, because the Soldered Inkplate
library silently swallows EPD-PMIC power-up failures:

```cpp
// InkplateLibrary/src/Inkplate.cpp
int Inkplate::einkOn() {
    …
    while ((readPowerGood() != PWR_GOOD_OK) && (millis() - timer) < 250);
    if ((millis() - timer) >= 250) {
        einkOff();
        return 0;          // ← failure
    }
    …
}

// InkplateLibrary/src/boards/Inkplate10.cpp
void Inkplate::display1b() {
    if (!einkOn()) return;  // ← void function; caller never learns
    …
}
```

When the TPS65186 PMIC fault-latches (over-current, thermal, VCOM stuck,
transient brownout), `readPowerGood()` never reaches `PWR_GOOD_OK` and
every subsequent `display.draw3bit()` / `partialUpdate()` becomes a
silent no-op. The firmware's `doFull` path runs to completion — fetch,
"draw," post-Full clock-zone cleanup, MQTT publish — and the panel never
moves. Recovery requires fully dropping VIN to the PMIC, which on this
hardware means **removing the LiPo** (the slider switch was insufficient
in this incident; bulk caps held VIN up).

Two failures are layered:

1. **Invisible.** Operators have no way to know the panel is wedged
   without physically looking at it.
2. **Unrecoverable in firmware.** Without a load-switch on the PMIC VIN
   rail, no software sequence (WAKEUP-low duration, I2C register reset,
   ESP32 cold boot) can clear the latch.

This proposal addresses (1) — observability — only. Fixing (2) requires
a hardware modification (load-switch MOSFET on PMIC VIN, or rerouting
the slider switch) and is tracked separately.

## What Changes

### A. Firmware

- Add `IDisplay::ensurePanelPower()` returning `bool`. Default impl
  returns `true` (host sim and any non-Inkplate target). `RealDisplay`
  delegates to `panel_.einkOn()` and reports its return value.
- `doFull` calls `ensurePanelPower()` immediately before the URL fetch.
  The result is logged via `FW_LOG` and threaded into the device-state
  JSON publish at the end of `doFull`.
- `battery::toDeviceStateJson` gains an `epd_pwrgood` bool argument and
  appends `"epd_pwrgood":true|false` to the JSON payload.
- When `ensurePanelPower()` returns false, the firmware still attempts
  the fetch+draw (zero marginal cost — Soldered's library will bail
  internally) and still publishes device state. The MQTT publish IS the
  recovery signal: HA is the operator's ear.

### B. HA

- New MQTT binary sensor `binary_sensor.inkplate_epd_pwrgood`
  (`device_class: problem`) mirroring the JSON field.
- New automation `inkplate_epd_pwrgood_alert` that fires
  `notify.inkplate_operator` with a clear "remove battery to recover"
  message when the binary sensor stays in `problem` state for ≥ 1 wake
  cycle (debounce against single-publish flaps).
- 4-hour re-notification throttle, matching the low-battery automation.

### C. Out of scope

- **Recovery.** Software cannot clear the PMIC fault latch on this
  hardware; the operator must physically remove the LiPo. A follow-up
  hardware change (load-switch MOSFET on PMIC VIN) is needed to make
  recovery automatable. Mentioned here only to clarify what this
  proposal does NOT promise.
- **Detecting partial-update wedges.** `doPartial` (the 1-min clock
  tick) also calls into `einkOn()` internally. We add the diagnostic
  only to `doFull` because (a) Fulls happen ≤ 30 min, fast enough for
  practical alerting, and (b) `doPartial` does not currently publish
  device state, so threading the flag through that path doubles the
  diff for marginal benefit.

## Why now

The issue produced an invisible 10-hour outage. Adding a single bool to
an existing MQTT publish is the cheapest possible failure-mode signal,
and lets us distinguish "panel wedged" from "rendering pipeline broken"
in any future incident — without USB.
