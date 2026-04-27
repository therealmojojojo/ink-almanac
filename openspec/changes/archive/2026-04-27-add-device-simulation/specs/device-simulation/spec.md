## ADDED Requirements

### Requirement: Hardware Abstraction Layer

The firmware SHALL expose all hardware interactions through a Hardware Abstraction Layer consisting of pure-virtual C++ interfaces (or equivalent compile-time polymorphism):

- `IDisplay` — operations: `drawImage(buffer, full|partial, rect)`, `clear()`, `refresh()`
- `IIMU` — operations: `init()`, `configureTap(threshold, duration)`, `configureDoubleTap(window)`, `readGyroBurst(duration_ms) → samples`
- `IPIR` — operations: `init()`, `armWake()`, `disarmWake()`
- `IBattery` — operations: `readVoltage() → float`, `readPercentage() → int`
- `IClock` — operations: `nowEpoch() → int64`, `sleepFor(seconds)`, `scheduleWake(wake_sources)`
- `ITransport` — operations: `wifiConnect()`, `httpGet(url) → response`, `mqttConnect()`, `mqttSubscribe(topic)`, `mqttPublish(topic, payload, retained)`, `mqttReadRetained(topic) → payload`

The main loop and wake-handling code SHALL reference only these interfaces — no direct calls into Soldered Inkplate library, Wire, WiFi, MQTT client libraries, or ESP32 sleep APIs.

Concrete implementations live in two builds: `hal/real/` for the device, `hal/mock/` for simulation.

#### Scenario: Main loop uses HAL only

- **WHEN** static analysis scans `firmware/src/main.cpp` and the core modules
- **THEN** no symbol from `Inkplate.h`, `Wire.h`, `WiFi.h`, `PubSubClient.h`, or `esp_sleep.h` appears; all hardware interaction is via HAL interfaces

#### Scenario: Same source compiles for both targets

- **WHEN** the host build and the device build are both invoked against the same firmware sources
- **THEN** both succeed, linking `hal/real/` and `hal/mock/` respectively

### Requirement: Mock implementations

The mock HAL SHALL provide instrumentable implementations suitable for scenario-driven testing:

- **MockDisplay** — records every `drawImage` call with timestamp, buffer hash, full-or-partial flag, and bounding rect. Exposes a query API: "how many full refreshes occurred?", "what was the last drawn bitmap hash?"
- **MockIMU** — scriptable INT events (tap, double-tap) with timestamps. Scriptable gyroscope readings as time-series arrays. Configuration calls are recorded.
- **MockPIR** — scriptable motion events with timestamps. Arm/disarm state observable.
- **MockBattery** — starts at configurable initial charge (default 100%). Voltage decreases based on accumulated simulated wake-time × current-draw per wake-source category (configurable curve). Exposes current charge state at any time.
- **MockClock** — simulated time. `sleepFor(seconds)` advances simulated time and updates battery accounting without real elapsed time. `nowEpoch()` returns the current simulated time.
- **MockTransport** — stubbed WiFi (always-connected by default, scriptable failures), stubbed HTTP (scripted responses keyed by URL), stubbed MQTT broker (in-memory retained messages, publish events observable).

All mocks SHALL be inspectable and scriptable via a test-facing API separate from the HAL interface.

#### Scenario: Recording display output

- **WHEN** a scenario fires a timer wake and the firmware fetches `/display/summary.png`
- **THEN** MockDisplay has one recorded `drawImage` call with `full=true`, the buffer hash matches the canned response from MockTransport, and the display state can be queried for assertions

#### Scenario: Scriptable gyroscope for door-filter tests

- **WHEN** a test injects a gyroscope profile corresponding to a 35°/s vertical-axis rotation for 800ms, then fires a tap INT 500ms later
- **THEN** MockIMU exposes the gyro samples to the firmware's door-filter logic, the filter decides to suppress, and MockTransport observes no tap-event MQTT publish

### Requirement: Scenario harness

Tests SHALL be expressible as ordered scenarios: a sequence of actions (time advances, sensor events, network events) with assertions after each action. The harness SHALL provide:

- Time control: `advanceTo(time)` and `advanceBy(duration)`
- Sensor injection: `firePIR()`, `fireTap(singleOrDouble, gyroProfile=None)`, `setBattery(percentage)`
- Network control: `mqttPublish(topic, payload, retained)`, `setRendererResponse(url, pngBuffer)`, `setWifiOnline(bool)`, `setMqttOnline(bool)`
- Query API: `lastDrawnMode()`, `partialRefreshCount()`, `batteryPercentage()`, `wakeSourcesArmed()`, `publishedMessages(topic)`
- Assertions using the host test framework (Catch2/doctest)

Scenarios SHALL be written in C++ (same as firmware) using the harness API.

#### Scenario: Writing a scenario

- **WHEN** a developer writes a scenario that simulates Summary hours for 30 minutes with 2 PIR events
- **THEN** the scenario compiles, runs in under 1 second of wall-clock time, advances simulated time 30 minutes, fires 2 PIR events at the scheduled instants, and the final assertions pass or fail per the scenario's expectations

### Requirement: Coverage parity with firmware specs

Every scenario in `device-firmware/spec.md` and `device-wake-protocol/spec.md` SHALL have a corresponding simulator test. When a firmware spec gains a new scenario, this test suite SHALL be updated to cover it in the same change.

#### Scenario: Spec scenario coverage

- **WHEN** `device-firmware`'s "Sleep strategy" requirement declares a scenario about Sonos fast-path activation
- **THEN** `firmware/test/scenarios/sleep_strategy_sonos_fast_path.cpp` (or equivalent) exists, runs, and passes

#### Scenario: New firmware scenario without coverage

- **WHEN** a pull request adds a scenario to `device-firmware/spec.md` without adding a corresponding simulator test
- **THEN** a pre-merge check (or at minimum documented convention) flags the missing test

### Requirement: Power-budget simulation

The simulator SHALL include a power-budget mode that runs a 42-day simulation (6 weeks) with a realistic daily usage pattern:

- Mode transitions at 06:30, 10:00, 22:00 every day
- 5 PIR events per day at simulated random active-hours times
- 2 tap events per day
- 1 Sonos session per day lasting 45 minutes within the Sonos-active window
- Constant MQTT and WiFi availability

At the end of 42 days, battery percentage SHALL be reported. The target is ≥20% remaining (≥80% capacity consumed, with 20% headroom for irregular days). If the simulation falls below 0% before day 42, the run fails.

Per-wake-source current-draw figures SHALL be configurable and documented in `firmware/docs/power-model.md`. The initial values are back-of-envelope and will be updated once real hardware measurements are taken.

#### Scenario: Power-budget pass

- **WHEN** the 42-day power-budget simulation runs with the current-draw parameters representing normal use
- **THEN** the simulation completes with battery ≥ 20%, and the report includes daily battery percentage, daily wake count by source, and total wake time

#### Scenario: Regression fails the budget

- **WHEN** a firmware change inadvertently doubles the Sonos fast-path frequency
- **THEN** the power-budget simulation completes with battery <20% (or fails entirely), and the failure message identifies the over-budget source

### Requirement: Door-filter test suite

The simulator SHALL include a corpus of recorded-or-synthesized gyroscope profiles covering:

- 10 realistic fridge-door-open events (different weights, speeds, hinge positions)
- 10 realistic fridge-door-close events
- 10 deliberate tap events with no rotation
- 10 edge cases: taps during slow near-static holds, taps immediately after a rotation ends

For each profile, the expected door-filter decision (suppress or allow) SHALL be labeled. The door-filter logic SHALL be evaluated against the full corpus and achieve:

- False-positive rate ≤ 5% (a tap suppressed when no rotation occurred, or a delivered tap when a rotation was active)
- False-negative rate ≤ 5% (a true tap suppressed erroneously, or a door-rotation delivered as a tap)

#### Scenario: Door-filter suite pass

- **WHEN** the door-filter suite runs against the current firmware thresholds
- **THEN** the false-positive rate is ≤ 5%, the false-negative rate is ≤ 5%, and per-profile decisions are reported

### Requirement: Dry-run against real renderer

A simulator mode SHALL allow MockTransport's HTTP stub to be replaced with a real HTTP client pointing at a running `renderer/` service on the same host. This tests the real renderer-device integration without the physical Inkplate.

MockDisplay captures the rendered PNG and can save it to disk for visual inspection; snapshot tests MAY be run against these captures.

#### Scenario: End-to-end dry run

- **WHEN** the operator runs the simulator in dry-run mode with the renderer running at `http://localhost:8575`, and fires a timer wake at 08:00 (Summary hours)
- **THEN** the simulator makes a real HTTP GET to the renderer, receives the rendered PNG, MockDisplay records the drawImage call, and the captured PNG is saved to `firmware/test/out/dry-run-summary.png` for review

### Requirement: Scenario authoring guidance

A document at `firmware/test/README.md` SHALL explain how to:

- Set up the host build target
- Write a new scenario (template + example)
- Add a new gyroscope profile to the door-filter suite
- Tune power-model parameters
- Run the suite locally and interpret the output

#### Scenario: Onboarding a contributor

- **WHEN** a new contributor reads `firmware/test/README.md`
- **THEN** they can run the existing scenarios successfully, add a new scenario that covers a specific spec requirement, and see it pass
