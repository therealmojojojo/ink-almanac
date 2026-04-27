## Context

The firmware's behavior is state-machine-shaped and power-sensitive. Every scenario the specs promise — Now-Playing fast-path activation, door-filter suppression, ghost-clear cadence, graceful degradation under network loss, 6-week battery budget — is non-trivial to verify on real hardware, and some are impossible to verify at all without instrumentation. The device doesn't exist yet, and even when it does, it will be mounted inside a frame on a fridge.

This change introduces a simulator that runs the exact firmware C++ code on the developer's machine against mocked hardware. It is modeled after common embedded-testing patterns: a HAL boundary at the library interface, dual implementations (real and mock), scenario-driven tests. Nothing here is novel; what matters is committing to the discipline now, before the firmware is written, so the structure supports it from day one.

Other testing layers (Python unit tests for pairing/ingestion, renderer snapshot tests, LLM fixture replay) are not in scope for this change. They live with their respective capabilities.

## Goals / Non-Goals

**Goals:**
- Every firmware spec scenario becomes a runnable test.
- The 6-week power budget becomes a computed value, regenerated on every change.
- Door-filter false-positive rate becomes measurable against a labeled gyroscope corpus.
- Renderer-to-device integration is testable end-to-end on a laptop.
- The firmware structure supports both simulation and real hardware from the same source.

**Non-Goals:**
- Perfect hardware fidelity. We will not simulate WiFi packet loss at the radio level, or battery temperature curves, or panel refresh artifacts. The goal is behavior correctness, not a digital twin.
- Testing the rendering pipeline here. The renderer's correctness is its own concern (snapshot tests live there).
- Replacing on-hardware validation. Once the device arrives, physical measurements still matter — especially for real tap thresholds and real PIR sensitivity in the kitchen.
- A common test framework across Python and C++. Different ecosystems, different conventions, kept separate.

## Decisions

### HAL boundary as an explicit requirement, not a convention

The spec pushes the HAL refactor back into `device-firmware` as a normative requirement. Rationale: without this, the simulator is a bolt-on that every firmware change has to accommodate manually. With it, the HAL becomes an invariant: no one can add hardware calls outside the HAL and expect the build to pass.

Alternative considered: document the convention in design only. Rejected because conventions drift without enforcement, and the simulator's value falls sharply as drift accumulates.

### C++ test framework, not a Python/Ruby shim

The firmware is C++. Running C++ scenarios in a Python harness (via SWIG or a subprocess protocol) adds indirection and fragility. A native C++ framework (Catch2, doctest) keeps the simulator self-contained and debuggable.

### Scriptable gyroscope samples, not a physics model

For the door-filter tests, we don't simulate hinge dynamics; we use recorded (or hand-synthesized) gyroscope sample timelines. Rationale: a physics model is imprecise anyway, and labeled real samples (captured from a dev-board prototype or synthesized to match expected shapes) are what we actually need — what does the filter do with *this* input?

### Power-budget simulation is a real test, not a spreadsheet

Spreadsheets are editable; tests regress. Moving the power budget into the simulator means it can't quietly drift. The test's accuracy depends on the per-source current-draw parameters, which are initially guesses and become real measurements once hardware arrives. The simulation's *shape* is correct regardless — what improves over time is the parameter realism.

### Dry-run against the real renderer, not a recorded snapshot

Rationale: the renderer is local (Mac host); running it during firmware tests is cheap. This exercises real network code, real HTTP parsing, real PNG decoding in the MockDisplay. The alternative — canned PNG responses — is simpler but doesn't catch renderer-firmware integration bugs.

### Scenario-spec parity is an explicit discipline

Every firmware spec scenario gets a test. This is the project's contract that specs and tests don't drift. It mirrors how OpenSpec itself tries to keep specs and code aligned, but at a lower level of abstraction.

### Coverage is scenario-based, not line-based

Line coverage is easy to game; scenario coverage means each expected behavior is exercised at least once. The simulator's tests are organized by scenario name, matching the spec language.

### The refactor happens inside `add-device-firmware`'s scope, but this change ratifies the requirement

The firmware change doesn't need to wait for this change to apply. Developers writing firmware for the first time should start with the HAL structure in place. The edit to `device-firmware`'s spec (adding the HAL-based-structure requirement) makes the constraint normative.

Alternative considered: lump everything into `add-device-firmware`. Rejected because simulation is a coherent, substantial concern that deserves its own reviewable surface. It also has different dependencies (the host build target, the mock implementations, the scenario harness) that don't belong in firmware-proper.

## Risks / Trade-offs

- **Mock behavior drifts from real hardware.** The LSM6DSO's tap detector has subtle register behavior; mocking it means we may write tests that pass against the mock but fail against silicon. Mitigation: once hardware arrives, a "bridge" phase validates the mock's behavior against the real sensor, and mock parameters are updated.

- **Time simulation can hide timing bugs.** A simulator advances time by function calls, not by wall-clock. Race conditions that occur on real hardware may not surface. Mitigation: scenarios explicitly test interleaved events (PIR during MQTT publish, tap during WiFi connect) to provoke race conditions deliberately.

- **Simulator maintenance overhead.** Every firmware change needs a corresponding test change. This is usually a feature (discipline), occasionally a drag. Mitigation: the scenario-authoring guide keeps the overhead per scenario small.

- **Power-budget parameters are initially fiction.** The first 42-day simulation result is only as accurate as the guess of "how much current does a WiFi-plus-render wake draw." Mitigation: clearly document that early numbers are placeholders; update in place when hardware measurements arrive; treat the simulator as a regression tool even before the absolute numbers stabilize.

- **Cross-compilation pain.** Compiling ESP32 Arduino code for the host is straightforward for logic but can hit issues with includes, pragmas, or compiler-specific features. Mitigation: keep the HAL thin; avoid ESP-specific types (like `IRAM_ATTR`) in the main loop; isolate platform-specific code to `hal/real/`.

- **Catch2/doctest choice trade-off.** Catch2 is richer but slower to compile; doctest is leaner. Defer; either is workable.

## Migration Plan

This change depends on `add-device-firmware` being a draft (so the HAL refactor can be baked in from the start). On apply:

1. Set up the host build target in PlatformIO.
2. Define the HAL interfaces in `firmware/include/hal/`.
3. Implement `hal/mock/` with all six interfaces.
4. Implement the scenario harness.
5. Translate the first set of firmware spec scenarios into tests.
6. Add the gyroscope profile corpus and door-filter test suite.
7. Add the power-budget simulation.
8. Add the dry-run-against-renderer mode.
9. Document in `firmware/test/README.md`.

Rollback: remove `firmware/test/` and the HAL-mocks target. The real firmware still works; only the test infrastructure is removed. The HAL itself remains — its cost is negligible at runtime and its discipline value is preserved.

## Open Questions

1. **Test framework.** Catch2 vs doctest vs GoogleTest. Defer to implementation; weakly lean doctest.

2. **Scenario file format.** Pure C++ scenarios are verbose but discoverable. A DSL (YAML or custom) would be terser but adds a parser. Probably start with pure C++ using a fluent API; consider a DSL later if scenarios pile up.

3. **Real-hardware validation gating.** Once hardware arrives, which simulator scenarios should be re-run against real hardware, and which are simulator-only? Probably: all "spec scenario" tests run against both; power-budget and door-filter run against real hardware for calibration; dry-run tests are pre-hardware only. Defer.

4. **MockTransport's MQTT semantics.** Do we model `retained` correctly? QoS levels? Reconnection behavior? Probably a minimal implementation sufficient for our scenarios, not a full broker. Document scope.

5. **Whether to track per-scenario energy and add energy budgets.** A specific scenario (e.g., "Summary mode morning cycle") could have its own energy budget that regresses if the cycle grows. Possibly overkill. Defer.
