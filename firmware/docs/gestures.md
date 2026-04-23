# Gestures

## Tap detection

The LSM6DSO provides hardware tap / double-tap detection. The firmware
configures registers `TAP_CFG0`, `TAP_THS_6D`, `TAP_DUR` and routes
`INT1` to an ESP32 GPIO as an `ext1` deep-sleep wake source.

On wake with `Reason::IMU`, the firmware:

1. Reads the tap kind from `TAP_SRC` (`DOUBLE_TAP` bit).
2. Publishes `{"kind":"single"|"double"}` on `inkplate/state/gesture`.

HA reacts to the gesture: single-tap → Weather peek; double-tap → toggle
Summary/Gallery.

## Latched-tap polling

Without INT1 wired to an ESP32 GPIO the device can't `ext1`-wake on a
tap. LSM6DSO's `LATCHED_INT` bit keeps the event visible across deep
sleep, so every Timer wake drains `TAP_SRC`; if a tap is pending, the
wake reason is upgraded to IMU. Worst-case latency is one timer period
(~60 s).
