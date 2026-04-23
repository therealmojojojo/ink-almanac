# Inkplate firmware

Thin-client ESP32 firmware for the Inkplate 10. Wakes, fetches a PNG from
the renderer, draws, sleeps.

## Status

This change (`add-device-firmware`) lands the firmware **logic** — the main
loop, wake/sleep strategy, LSM6DSO tap handling, battery reporting, MQTT
contracts — exercised via the host simulator from `add-device-simulation`.

Hardware is not yet available. The real HAL wrappers under
`src/hal/real/` are compile-guarded skeletons; detailed driver code lands
once an Inkplate 10 + LSM6DSO + PIR are on the bench. Until then, verify
behavior with `firmware_sim`.

## Directory layout

```
firmware/
├── include/                  public headers
│   ├── hal/                  interfaces (add-device-simulation)
│   ├── config.h              all tunables
│   ├── modes.h wake.h gestures.h battery.h
│   ├── firmware.h            `fw::tick(hal, reason)`
│   └── secrets.h.example
├── src/
│   ├── modes.cpp wake.cpp gestures.cpp battery.cpp
│   ├── main_loop.cpp         the tick
│   ├── main.cpp              on-device entry (ARDUINO-guarded)
│   └── hal/real/             real-HAL wrappers (ARDUINO-guarded)
├── test/                     host simulator (add-device-simulation)
│   ├── hal/mock/             mock HAL
│   ├── harness/              scenario harness
│   ├── scenarios/            spec-driven tests
│   ├── power/                42-day power-budget sim
│   └── main.cpp              doctest entry
├── CMakeLists.txt            native host build
├── platformio.ini            native + esp32 targets
└── docs/                     config, gestures, wake-protocol, power-budget
```

## Building the host simulator

```bash
cd firmware
# doctest header
curl -L https://raw.githubusercontent.com/doctest/doctest/master/doctest/doctest.h \
  -o test/third_party/doctest/doctest.h
# build + run
cmake -B build -S .
cmake --build build -j
./build/firmware_sim
```

## Flashing the device (once hardware arrives)

```bash
cp include/secrets.h.example include/secrets.h
# edit include/secrets.h
pio run -e inkplate10 -t upload
pio device monitor
```

Subsequent flashes can use OTA:

```bash
pio run -e inkplate10 -t upload --upload-port 192.168.1.42
```

## Main loop

See `src/main_loop.cpp`. One wake = one call to `fw::tick(hal, reason)`:

1. Identify wake reason (ESP32 wake API on device; explicit arg in tests).
2. IMU wake → read tap kind from `TAP_SRC`.
3. WiFi + MQTT connect.
4. Resolve active mode: MQTT retained `inkplate/command/active_mode`
   or time-of-day fallback.
5. Fast-path early-return if `SonosFastPath` reason + unchanged mode.
6. Fetch PNG (3 retries with back-off). On failure: corner indicator.
7. Full refresh on mode change / cold boot / post-OTA / ghost-cadence
   threshold. Partial refresh otherwise.
8. Publish device state + any gesture over MQTT.
9. Arm wake sources; caller enters `sleepFor`.

(Motion-triggered wakes arrive as `ha_command`; the former on-device PIR
path was removed with the HA-motion migration. See
`openspec/changes/move-pir-to-ha-motion/`.)

## Debugging

Every wake publishes `inkplate/state/device` with
`{voltage, percentage, wake_reason, active_mode, build}`. Watch that
topic in HA to see which path each wake took.
