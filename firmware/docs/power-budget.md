# Power budget

The authoritative simulation lives in
`firmware/test/power/power_budget.cpp`. This document captures the back-of-
envelope math used to set the initial per-source current-draw values in
`firmware/docs/power-model.md`.

## Target

6 weeks (42 days) between charges on a 5000 mAh LiPo, with 20 % headroom
remaining at day 42 (i.e. ≤ 80 % of nominal capacity consumed).

Hardware budget:

| Category | Assumption | Rationale |
| -------- | ---------- | --------- |
| Pack capacity | 5000 mAh | Soldered single-cell LiPo |
| Nominal voltage | 3.7 V | LiPo midpoint |
| Usable energy | 4000 mAh × 3.7 V ≈ 14.8 Wh | 20 % reserve |

## Per-wake breakdown

Per-wake is the dominant cost. The budget works if:

- Active wakes ≤ 90 mA × 12 s average = 1.08 mAh per wake.
- Quiescent ≤ 150 µA between wakes.
- Summary + Weather hours: 1 wake per 15 min × 14 h = 56 wakes.
- Gallery / Night: 1 wake per 60 min × 10 h = 10 wakes.
- PIR wakes: ≤ 5/day × shorter (≤ 6 s) active time.
- Sonos fast-path: up to 1 per 3 min × 13 h = 260 checks/day, but most
  early-return (no mode change) in ~0.5 s active time.

Daily active mAh budget: (56 + 10) × 1.08 + 5 × 0.45 + 260 × 0.04 ≈
**83 mAh/day active** + 3.6 mAh/day quiescent ≈ **86.6 mAh/day**.

42 days × 86.6 mAh = **3637 mAh** → under 4000 mAh budget with headroom.

## Validation

The simulator runs this profile with `MockBattery` applying per-source
currents tracked in `firmware/docs/power-model.md`. The assertion
`battery ≥ 20 % at day 42` fails loudly on any change that inadvertently
pushes the budget past the ceiling.

## Post-hardware recalibration

1. Instrument the device with a power profiler.
2. Capture the mean current for each wake category.
3. Update `firmware/docs/power-model.md` and `Scenario.cpp` defaults.
4. Re-run `./build/firmware_sim --test-case="power-budget*"`.

The initial simulation uses placeholder values; once hardware is
instrumented, a single set of measurements replaces them all.
