# Prevent TPS65186 partial-power wedge

> **Status — 2026-05-18**: draft, code in flight; depends on
> `add-epd-power-good-diagnostic` (archived 2026-05-04) for the existing
> `ensurePanelPower` probe and `binary_sensor.inkplate_device_epd_power_good`
> wiring.

## Why

On 2026-05-17 21:59 local the panel froze on a stale Gallery face. The
operator was paged at 22:30 by the existing
`inkplate_epd_pwrgood_alert` automation (debounced 31 min, per
`add-epd-power-good-diagnostic`) but didn't see the notification until
the next morning. Twelve hours of consecutive wake cycles all reported
`epd_pwrgood: false`; the firmware was healthy at every level except
the e-ink write itself.

A USB diagnostic build (`firmware/src/epd_probe.cpp`) dumped the PMIC
register state. The chip was alive on I²C (REVID `0x66`, ACKing at
0x48) but **PWR_GOOD = 0xA0** — a partial-rail configuration:

| Bit | Rail | State |
|---|---|---|
| 7 | VPOS | OK |
| 6 | VEE  | BAD |
| 5 | VNEG | OK |
| 4 | VDDH | BAD |
| 3 | VB   | BAD |

Critically: **INT1 = 0x00 and INT2 = 0x00**. No fault was latched
(no thermal shutdown, no over-current on any rail, no UVLO). The chip
was not faulted in the TI silicon sense — it was in a sequencer-
confusion state where the rail monitors disagreed and the power-up
sequencer refused to proceed.

Four graduated software recovery attempts — plain `einkOn()`,
`einkOff() + 2 s + einkOn()`, dropping WAKEUP low for 500 ms via direct
expander writes then `einkOn()`, and a full `UPSEQ0/DWNSEQ0` re-init —
all left `PWR_GOOD` at 0xA0. Only physically removing the LiPo battery
for ~30 s recovered the chip; on cold-boot `PWR_GOOD` reads `0xFA` and
`einkOn()` returns 1 immediately.

The byte pattern matches [Inkplate-Arduino-library
issue #297](https://github.com/SolderedElectronics/Inkplate-Arduino-library/issues/297)
(open since March 2026, no maintainer response, board-independent).
That report's diagnosis — Soldered's `TPS65186::powerDown()` leaves
rails partially asserted because the library waits at most 250 ms for
`readPowerGood()` to reach 0, then forces `enableRails(false)` over
I²C regardless of actual rail state — is consistent with both our
code-level reading of `src/features/TPS65186/TPS65186.cpp` and our
diagnostic data. The chip's enable bit goes to 0; the rails sometimes
don't.

The `add-epd-power-good-diagnostic` change (April 2026) made this
failure *visible* but didn't prevent it. This change prevents it.

## What changes

**Device firmware:**

- Add `IDisplay::ensurePanelDown(timeout_ms = 3000)` and
  `IDisplay::readPwrGoodByte()`. The Real implementation calls
  `panel_.einkOff()` (idempotent) then polls TPS65186 register 0x0F
  directly via I²C until it reads 0x00 (rails actually collapsed) or
  0xFF (chip non-responsive, treated as off), with a 3-second budget.
  Returns false if rails stayed partially up — that is the wedge-entry
  moment.
- Call `ensurePanelDown` at the end of every `doFull` wake, after the
  draw and before the MQTT state publish. The poll loop physically
  gives rails up to 3 s + library's own 250 ms to drain — a 13× headroom
  over the library's hard-coded cap. On a healthy chip the rails reach
  0 in ~100-200 ms so the cost is small.
- Publish two new fields in `inkplate/state/device`:
  `"epd_pg_raw": "0xNN"` (raw PWR_GOOD byte) and `"epd_down_clean": bool`
  (whether rails reached 0 within timeout). These ride alongside the
  existing `epd_pwrgood` bool so HA can distinguish "wedged at 0xA0"
  from "chip not even responding" from "healthy."

**HA integrations:**

- Add MQTT sensors mirroring the new JSON fields:
  `sensor.inkplate_device_epd_pg_raw` (the raw hex byte, useful in
  Developer Tools / templates) and
  `binary_sensor.inkplate_device_epd_down_clean`
  (device_class: problem, on = unclean).
- Add a pre-emptive alert automation that fires the same notify channel
  as `inkplate_epd_pwrgood_alert` when `epd_down_clean = false` on two
  consecutive wakes — that's the operator's *advance warning* that the
  wedge is about to happen, hours before `epd_pwrgood` actually goes
  false on the following wake.

## Scope

In: device firmware HAL extension + JSON payload + HA sensors + alert.
Not in: forking the Soldered library, hardware load-switch on PMIC VIN
(captured separately as a future hardware change), or auto-recovery
sequences beyond what `ensurePanelDown` already attempts (the diagnostic
proved nothing else works in software).

## Risks

- **Extra wake duration.** ~50-200 ms on a healthy chip, up to 3 s when
  the wedge is entered. Negligible against the 15-30 minute cadence.
- **False-positive `epd_down_clean=false` reports.** If a transient
  I²C glitch makes the polling read garbage other than 0x00 / 0xFF for
  the entire 3 s window, we'd publish a false alarm. The 2-consecutive
  debounce in the HA alert side absorbs this.
- **The wedge can still happen.** Our 3 s budget greatly extends the
  drain window but cannot guarantee discharge under every load. The
  hardware mod (MOSFET on VIN) remains the only fully-deterministic
  fix, deferred to a separate change.
