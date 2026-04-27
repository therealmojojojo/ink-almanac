# Power model

Per-source current-draw parameters used by the simulator's `MockBattery`. These
are **placeholders** until proper hardware measurements arrive — values are
educated guesses suitable for relative comparison (does change X make the
battery last longer or shorter?) but not for absolute lifetime prediction.

| Source | mA | Notes |
| ------ | -- | ----- |
| `deep_sleep` | 0.15 | Quiescent with RTC + IMU INT1 wake armed |
| `active_summary` | 90 | WiFi assoc + HTTP fetch + panel full refresh |
| `active_weather` | 90 | Same shape as summary |
| `active_gallery` | 90 | Same shape as summary |
| `active_night` | 85 | No partial-refresh cadence, smaller per-wake delta |
| `active_now_playing` | 90 | Per-minute Full while Sonos is playing |
| `wifi_connect` | 140 | Association burst (not per-wake; optional) |
| `pir_wake` | 75 | Legacy — PIR moved to HA, retained for backward compat in scenarios that still reference it |

`pir_wake` is a vestigial entry — on-device PIR was removed (motion now
arrives as `HACommand`) but the simulator entry stays so old test
scenarios keep loading.

## Capacity

The **simulator** assumes **2000 mAh** as a conservative default in
`firmware/test/harness/Scenario.cpp` (set via `MockBattery::setCapacity`).
This is a stress-test capacity, not the cell on the actual device — the
operator's hardware uses a 5000 mAh LiPo (see `power-budget.md`), so the
real device runs ~2.5× the runtime the simulator predicts.

The 2000 mAh stress value is deliberate: the power-budget regression
threshold ("battery ≥ 20% at day 42") is calibrated against the smaller
cell so any change that pushes the simulator below 20% would be far worse
on a smaller real-world cell, and any change that passes against 2000 mAh
will pass against 5000 mAh too. To switch the simulator to the real
hardware capacity, change the constructor default in `Scenario.cpp` and
re-baseline the day-42 assertion.

## Recalibration process

1. Instrument a bench ESP32 + Inkplate 10 with a power meter (e.g., Power Profiler Kit II).
2. For each source above, capture the mean current during the category's
   active window.
3. Replace the row in this file.
4. Update `test/harness/Scenario.cpp` ctor defaults.
5. Re-run `./build/firmware_sim --test-case="power-budget*"` and check for
   regressions.

## Pass/fail

The power-budget test asserts **battery ≥ 20% at day 42**. Any firmware change
that pushes this below 20% (e.g. an unexpected extra wake path) fails CI.
