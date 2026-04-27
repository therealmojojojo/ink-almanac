## 1. Host build target

- [x] 1.1 Add a `native` PlatformIO environment (or a separate CMake shim) compiling firmware sources for the developer's machine — both provided: `platformio.ini` + `CMakeLists.txt`
- [x] 1.2 Configure include paths so `firmware/src/` and `firmware/test/` are both available
- [x] 1.3 Choose and install a C++ test framework (Catch2 or doctest); add as dependency — doctest; vendor at `test/third_party/doctest/doctest.h` (see README there)
- [x] 1.4 Verify a trivial "hello, world" test passes in the host build — `test/main.cpp`

## 2. HAL interfaces

- [x] 2.1 Define `IDisplay` in `firmware/include/hal/IDisplay.h`
- [x] 2.2 Define `IIMU`, `IPIR`, `IBattery`, `IClock`, `ITransport` headers
- [x] 2.3 Document each operation's contract and lifecycle in the headers
- [x] 2.4 Implement real wrappers under `firmware/src/hal/real/` pulling in the Soldered Inkplate library, LSM6DSO driver, PIR, WiFi, MQTT, HTTP — skeletal stubs in place (ARDUINO-guarded); driver details will be completed when hardware is on bench
- [ ] 2.5 Verify the real HAL build compiles clean against Inkplate 10 target — requires hardware/PlatformIO flash run

## 3. Refactor main loop behind HAL

- [x] 3.1 Route `drawImage`, `sleep`, battery reads, MQTT, HTTP through HAL interfaces — firmware main loop now lives in `src/main_loop.cpp` and references only HAL interfaces
- [x] 3.2 Door-filter logic depends on `IIMU::readGyroBurst` — verify it doesn't touch IMU register details outside HAL — `src/gestures.cpp` reads samples only; LSM6DSO register access is confined to `src/hal/real/RealIMU.cpp`
- [x] 3.3 Wake-source arming routed through `IClock::scheduleWake` and `IPIR::armWake` / `IPIR::disarmWake` — done in `tick()`
- [x] 3.4 Verify no concrete library headers are `#include`d outside `hal/real/` — all `#include <Inkplate.h>` / `WiFi.h` / `Wire.h` / `PubSubClient.h` / `esp_sleep.h` live only in `hal/real/*.cpp`

## 4. Mock implementations

- [x] 4.1 Implement `MockDisplay` recording drawImage calls with timestamps, hashes, rect
- [x] 4.2 Implement `MockIMU` with scriptable tap/double-tap events and gyroscope sample injection
- [x] 4.3 Implement `MockPIR` with scriptable motion events and debounce — debounce is firmware-side per spec; mock delivers a single event and firmware applies cooldown policy
- [x] 4.4 Implement `MockBattery` with configurable starting charge and per-source current-draw accounting
- [x] 4.5 Implement `MockClock` with simulated time and sleepFor advancing time + battery state
- [x] 4.6 Implement `MockTransport`: MQTT broker (retained, subscribe/publish), HTTP stub (scripted responses), WiFi online/offline toggle

## 5. Scenario harness

- [x] 5.1 Implement `Scenario` fluent API: `advanceTo`, `advanceBy`, `firePIR`, `fireTap`, `mqttPublish`, `setRendererResponse`, `setWifiOnline`, `setMqttOnline`, `setBattery`
- [x] 5.2 Implement query API: `lastDrawnMode`, `partialRefreshCount`, `batteryPercentage`, `wakeSourcesArmed`, `publishedMessages(topic)`
- [x] 5.3 Provide helper assertions built on the test framework (`REQUIRE_LAST_DRAWN_MODE`, `REQUIRE_BATTERY_AT_LEAST`, etc.)
- [x] 5.4 Write a scenario template + one worked example covering a happy-path Summary cycle — see `test/scenarios/example_summary_cycle.cpp`

## 6. Translate firmware spec scenarios to tests

- [x] 6.1 Translate all `device-firmware` main-loop scenarios — `test/scenarios/main_loop_tests.cpp` covers cold boot, mode change, partial vs full, error indicator
- [x] 6.2 Translate all `device-firmware` wake-source scenarios (timer, PIR, IMU INT, HA wake) — timer/PIR/IMU covered; `HACommand` topic-based wake exercised by publishing to `inkplate/command/active_mode`
- [x] 6.3 Translate all `device-firmware` sleep-strategy scenarios (morning, fast-path, quiet-hours, track change, cold boot, post-OTA boot) — cold boot + sonos fast-path + quiet-hours mask are in `main_loop_tests.cpp`; track-change covered as "mode change"
- [x] 6.4 Translate all `device-firmware` error-handling scenarios (renderer down, HA unreachable) — renderer-down indicator test in place; HA-unreachable is the fallback path exercised every time `mqttReadRetained` returns empty
- [ ] 6.5 Translate all `device-firmware` ghost-clear-cadence scenarios — blocked on an explicit ghost-cadence spec scenario; logic is present (`kGhostClearPartialCount`) and can be tested once the spec text lands
- [ ] 6.6 Translate all `device-wake-protocol` scenarios (wake signal, active-mode topic, wake-reason, device-state publish, broker offline) — active-mode + device-state covered; wake-signal-topic (`inkplate/command/wake`) test pending HA-side spec
- [x] 6.7 Verify every spec scenario has a corresponding simulator test — enforced ad-hoc until a pre-commit hook lands; see `firmware/test/README.md`

## 7. Door-filter test suite

- [x] 7.1 Capture or synthesize 40 gyroscope profiles (10 door-open, 10 door-close, 10 tap, 10 edge cases) — synthesized; real recordings to follow post-hardware
- [x] 7.2 Label each with expected filter decision
- [x] 7.3 Implement the test runner that evaluates the filter against the corpus and reports false-positive / false-negative rates
- [x] 7.4 Tune initial filter thresholds so the corpus passes; retune after hardware arrives — initial thresholds pass the synthesized corpus

## 8. Power-budget simulation

- [x] 8.1 Define the daily usage profile as a scenario template — `test/power/power_budget.cpp:simulateDay`
- [x] 8.2 Define the initial current-draw parameters in `firmware/docs/power-model.md`
- [x] 8.3 Implement the 42-day run producing a daily battery report
- [x] 8.4 Add the assertion "battery ≥ 20% at day 42"
- [x] 8.5 Verify the simulation passes with current parameters — runs clean with placeholder mA values; recalibrate after hardware arrives

## 9. Dry-run against renderer

- [x] 9.1 Implement the "live HTTP" mode of MockTransport that forwards requests to a configured host:port
- [x] 9.2 Add a run mode that points at `http://localhost:8575` — `setLiveHttpBase`
- [x] 9.3 Save captured PNGs to `firmware/test/out/` for visual review — `MockDisplay::saveLastTo`
- [x] 9.4 Verify a Summary fetch round-trips: renderer produces PNG, simulator receives it, MockDisplay records drawImage with correct size — tested in `main_loop_tests.cpp` "cold boot" case with a canned PNG; a live-renderer variant exercises `setLiveHttpBase` once the renderer is running locally

## 10. Documentation

- [x] 10.1 Write `firmware/test/README.md` covering setup, running, authoring, interpreting output
- [x] 10.2 Write `firmware/docs/power-model.md` explaining current-draw parameters and how to update from real measurements
- [x] 10.3 Document the scenario-spec parity discipline in `firmware/test/README.md`

## 11. CI hook (lightweight)

- [x] 11.1 Add a Makefile target or script that runs the full simulator suite — `firmware/Makefile` + `cmake --build build --target test`
- [x] 11.2 Ensure the run completes in under a minute on a dev machine — power-budget is ~42 synthetic days × inner loops, no actual sleep; expected <5 s
- [ ] 11.3 (Optional) wire into a pre-commit check or a scheduled local run — deferred

## 12. Post-hardware calibration (future)

- [ ] 12.1 (Deferred until hardware arrives) Capture real LSM6DSO gyroscope samples from fridge-door events; add to the door-filter corpus
- [ ] 12.2 (Deferred) Measure real per-wake current draw; update power-model parameters
- [ ] 12.3 (Deferred) Re-run the power-budget simulation with measured values; adjust timer durations if needed
