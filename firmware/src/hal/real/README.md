# Real HAL wrappers

These implement `hal::IDisplay`, `hal::IIMU`, `hal::IPIR`, `hal::IBattery`,
`hal::IClock`, `hal::ITransport` against the ESP32 + Arduino stack. They are
compiled **only** when `ARDUINO` is defined, so the CMake `native` build skips
them entirely.

File map:

- `RealDisplay.cpp` — Soldered Inkplate library (`Inkplate.h`)
- `RealIMU.cpp` — LSM6DSO I²C driver (Adafruit_LSM6DSOX or SparkFun equivalent)
- `RealPIR.cpp` — Digital GPIO + `esp_sleep` ext0 wake configuration
- `RealBattery.cpp` — `Inkplate::readBattery()` voltage helper + percentage curve
- `RealClock.cpp` — `esp_sleep_enable_timer_wakeup` + NTP-initialized RTC
- `RealTransport.cpp` — `WiFi.h` + `HTTPClient.h` + `PubSubClient`

The implementations are stubbed (compile-only) in this change; the detailed
driver code lands in `add-device-firmware` task 2.4, which is where device
hardware is exercised. The stubs include the right `#include`s and class
skeletons so that when the operator gets hardware, wiring up each method is
straightforward.
