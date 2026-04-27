## Why

The firmware carries the project's most nuanced behavior: the sleep strategy, the tap-vs-door discrimination, the override precedence, the ghost-clear cadence, the graceful-degradation paths when server-side is unreachable. It is also the hardest to iterate on because the physical device doesn't exist yet, and even when it does, debugging a deep-sleeping ESP32 stuck on the fridge is not a tight feedback loop.

This change introduces a host-side simulator that runs the exact firmware code against mocked hardware — display, IMU (LSM6DSO), PIR, battery, RTC clock, WiFi, MQTT — plus a scenario harness that drives the simulator through scripted timelines and asserts expected outcomes. Every scenario in `device-firmware` and `device-wake-protocol` becomes a runnable test. Power budget becomes a computed value, not a hope.

This change is specific to device simulation; unit tests for Python pairing/ingestion code, renderer snapshot tests, and LLM fixture tests live in their own changes. The common thread here is that the firmware's main behaviors are state-machine-shaped and benefit from the same compile-once, mock-hardware, replay-scenarios discipline.

## What Changes

- Refactor the firmware (within `add-device-firmware`) behind a thin Hardware Abstraction Layer (HAL): `IDisplay`, `IIMU`, `IPIR`, `IBattery`, `IClock`, `ITransport` (WiFi + HTTP + MQTT). Real implementations on-device, mock implementations in simulation. The same C++ source compiles for both targets.
- Introduce a **host build target** in PlatformIO (or a CMake shim) that compiles the firmware for the developer's machine with the mock HAL linked.
- Implement **mock sensors** with realistic behaviors:
  - Mock LSM6DSO: scripted tap/double-tap INT events, scripted gyroscope timelines (for door-filter testing), configurable thresholds.
  - Mock PIR: scripted motion events with debounce.
  - Mock battery: voltage/percentage curve advanced as the simulator accumulates "wake time × current draw" per source.
  - Mock display: drawImage calls recorded with full/partial refresh flag and bounding rect; ghost-cadence counter observable.
  - Mock clock: simulated time, advanceable by tests; deep-sleep durations are consumed as time advances.
  - Mock transport: stubbed HTTP (respond with canned PNGs), stubbed MQTT broker (retained messages, subscribe/publish).
- Introduce a **scenario harness**: tests are written as timelines of actions (advance time, fire PIR, publish MQTT, inject tap with specific gyroscope profile, go offline) with assertions after each action.
- Translate **every scenario from the `device-firmware` and `device-wake-protocol` specs** into a simulator test. Every spec scenario becomes a runnable, auditable test case. New scenarios added to those specs get added here too.
- Implement a **power-budget simulation** that accumulates wake duration × current draw over a simulated 6-week period and reports projected battery state. A regression here fails loudly if a new wake path blows the budget.
- Implement a **door-filter test suite** with recorded gyroscope profiles representing realistic fridge-door opens and closes (multiple door weights, speeds, hinge locations). The 5% false-positive target becomes measurable.
- Implement a **"dry-run against real renderer"** mode where the simulated device talks to the actual `renderer/` service over LAN, so integration between renderer and device is testable end-to-end without the real Inkplate.
- Provide a **scenario-authoring guide** so new behavior added to firmware gains test coverage as naturally as new Python code gains Pytest coverage.

## Capabilities

### New Capabilities

- `device-simulation`: The host-side firmware simulator — HAL abstractions, mock implementations, scenario harness, power-budget accounting, test coverage for every firmware specification scenario.

### Modified Capabilities

- `device-firmware`: Amended to require the HAL-and-mocks structure (interfaces, not concrete hardware calls in the main loop) so the firmware is testable. The behavioral requirements already specified stand; this adds a testability constraint.

## Impact

- **New directory**: `firmware/test/` with the host build target, HAL interfaces, mock implementations, scenario harness, scenario files.
- **Additional PlatformIO environment**: the `native` or host environment using the system compiler rather than `xtensa-esp32-elf-gcc`.
- **New dependencies**: a C++ test framework (Catch2 or doctest — both header-only, Arduino-friendly), possibly GoogleTest. Choice deferred to implementation.
- **CI**: this test suite runs on every commit to the firmware, on the developer's machine (no hardware required). CI setup is deferred but implied.
- **Firmware refactor cost**: pulling the main loop behind a HAL is roughly a day of work but unlocks all of the above. This change formalizes the refactor.
- **No runtime impact on the device**: the HAL abstraction is compile-time; the production build has identical performance to a direct-call implementation.
