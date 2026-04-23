# Power model

Per-source current-draw parameters used by the simulator's `MockBattery`. These
are **placeholders** until hardware measurements arrive.

| Source | mA | Notes |
| ------ | -- | ----- |
| `deep_sleep` | 0.15 | Quiescent with RTC + PIR wake armed |
| `active_summary` | 90 | WiFi assoc + HTTP fetch + panel full refresh |
| `active_weather` | 90 | Same shape as summary |
| `active_gallery` | 90 | Same shape as summary |
| `active_night` | 85 | No full refresh cadence, smaller deltas |
| `active_now_playing` | 90 | Partial refresh per track change |
| `wifi_connect` | 140 | Association burst (not per-wake; optional) |
| `pir_wake` | 75 | Short render + back to sleep |

## Capacity

Assumed pack capacity: **2000 mAh** (single 18650 cell). Update
`MockBattery::capacity_mah_` when the final pack is chosen.

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
