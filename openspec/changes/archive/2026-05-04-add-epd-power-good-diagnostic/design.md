# Design — EPD power-good diagnostic

## Why we can't fix the wedge in firmware

The TPS65186-class EPD PMIC on Inkplate 10 has fault latches that, once
tripped, refuse to assert `PWR_GOOD` until VIN drops to 0 V long enough
to drain the chip's internal state. Confirmed empirically on the
2026-04-30 incident: no software path (begin(), einkOff/einkOn cycle,
ESP32 cold boot via serial-port-open) cleared it. Only LiPo removal
worked.

The Soldered library's failure path is structurally invisible:

| Layer | Behavior on einkOn failure |
|---|---|
| `Inkplate::einkOn` | returns 0 |
| `Inkplate10::display3b` (and partialUpdate paths) | `if (!einkOn()) return;` — bail silently |
| Public API `display.draw3bit()` / `partialUpdate*()` | `void` return; caller has no signal |

So our firmware's `doFull` thinks every step succeeded.

## What we add, and why this shape

### `IDisplay::ensurePanelPower() → bool`

A small probe the firmware calls explicitly before the fetch+draw. It
delegates to `panel_.einkOn()` (idempotent — if the panel is already
powered, the library returns 1 immediately without doing extra work).
The bool comes back to firmware logic, which can log it and thread it
into MQTT.

Alternatives considered:

- **Read `readPowerGood()` directly.** Rejected: that register is only
  meaningful while the chip is powered up. Calling it from a cold state
  always returns 0; calling it after a successful draw always returns
  `PWR_GOOD_OK`. Useless as a wedge signal.
- **Wrap `drawImageFromUrl` to return failure on einkOn miss.** Rejected:
  the library doesn't propagate `einkOn`'s return through `drawImage`.
  We'd have to fork or shim around it. A pre-call probe is simpler.
- **Detect a wedge after the fact** (canary pixel hash, framebuffer
  read-back). Rejected: requires reading panel SRAM, which the Soldered
  library doesn't expose for Inkplate 10. Adds significant complexity
  for a signal we can get cheaper from `einkOn`.

### `epd_pwrgood` in the device-state JSON

Threading a single bool through `toDeviceStateJson` is one new arg, one
JSON field. The field appears on every full-cycle wake (≤ 30 min in
Midday, ≤ 15 min Morning/Evening, ≤ 15 min Night), giving HA a fresh
signal at the same cadence as battery and active_mode.

Partial wakes (the minute clock tick) do not publish device state. We
accept up to ~30 min detection latency — well below the human-noticing
threshold and well below the 10 h actual incident.

### HA: binary_sensor + 1-cycle debounce

A `device_class: problem` binary sensor reads the JSON field. The
notification automation requires the sensor to be in `problem` state
across two consecutive publishes (`for: "00:31:00"` covers the worst
Midday cadence) before notifying. This protects against single transient
PMIC retries — if the next wake's `einkOn` succeeds, no alert fires.

Rejected: notify on first occurrence. Operationally too noisy if the
PMIC ever has a self-healing transient.

Rejected: include the diagnostic in the renderer's `/inputs/device`
publisher path. The renderer's device input is operator-facing summary;
PMIC-level health belongs in HA's diagnostics, not in panel content.

## Cost

- One extra `einkOn()` call per Full (no-op if already powered, ~10 ms
  for I2C transactions if from cold). Fulls happen 4-6 times per hour
  peak. Negligible battery cost.
- One bool field in the device-state JSON (~17 bytes).
- One new HA binary sensor + one automation file.

## Risks

- **`einkOn()` side-effects on probe.** `einkOn` does I2C config writes
  to the TPS65186 and toggles WAKEUP. If a draw was about to happen
  anyway, our probe is a no-op. If no draw was going to happen (we abort
  on `false`), the panel is left powered for the post-Full state publish
  — `einkOff` is called only after the next library draw call. Mitigation:
  call `display.einkOff()` ourselves if we abort the draw. Marginal.
- **JSON schema bump.** `epd_pwrgood` is a new field. HA's JSON
  value_template tolerates missing keys silently. The renderer's
  `/inputs/device` path reads `battery`/`build`/`last_seen` only; it
  ignores extra fields. No coordinated rollout needed.
