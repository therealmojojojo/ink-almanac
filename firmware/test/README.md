# Firmware simulator

Host-side test harness for the Inkplate firmware. Runs the real firmware C++
against mocked hardware — display, IMU, PIR, battery, clock, WiFi, HTTP, MQTT.

## Setup

```bash
cd firmware
curl -L https://raw.githubusercontent.com/doctest/doctest/master/doctest/doctest.h \
  -o test/third_party/doctest/doctest.h
cmake -B build -S .
cmake --build build
./build/firmware_sim
```

Or run via CTest:

```bash
cmake --build build --target test
```

## What's in this change

This change (add-device-simulation) lands:

- `firmware/CMakeLists.txt` + `platformio.ini` (native + esp32 targets)
- `firmware/include/hal/*.h` — interfaces: `IDisplay`, `IIMU`, `IPIR`, `IBattery`, `IClock`, `ITransport`
- `firmware/test/hal/mock/*` — mock implementations with inspection APIs
- `firmware/test/harness/Scenario.{h,cpp}` — fluent scenario API
- `firmware/test/scenarios/*.cpp` — worked examples
- `firmware/test/door_filter/` — synthesized gyroscope corpus + filter + test
- `firmware/test/power/` — 42-day power-budget simulation
- `firmware/docs/power-model.md` — per-source current-draw parameters

It does NOT land:

- `firmware/src/hal/real/` — real HAL wrappers (`add-device-firmware`)
- `firmware/src/main.cpp` — main loop refactored behind the HAL
  (`add-device-firmware` with HAL-based-structure requirement)
- Translated spec scenarios — these pair with firmware spec scenarios added
  in `add-device-firmware`; the tests will be written there (see task 6.x
  in `add-device-simulation/tasks.md`).

## Writing a scenario

```cpp
#include "doctest.h"
#include "harness/Scenario.h"

TEST_CASE("summary morning cycle") {
  sim::Scenario s;
  s.clock().setNow(1'744'617'600);
  s.setBattery(95)
      .setRendererResponse(
          "http://renderer.local:8575/display/summary.png", canned_png())
      .advanceTo(6 * 3600 + 30 * 60)  // 06:30
      .fireTap()
      .advanceBy(10);

  // Once the firmware main loop is linked, call its tick function here.
  // fw::tick(s.hal(), fw::wake::Reason::IMU);

  REQUIRE(s.display().fullRefreshCount() == 1);
  REQUIRE(s.batteryPercentage() >= 90);
}
```

## Adding a door-filter profile

`door_filter/door_filter.cpp:synthesizeCorpus()` owns the initial synthesized
profiles. Add real recordings as `.csv` files under `door_filter/profiles/`
(one row per sample, columns: `t_ms,x,y,z`) and load them via a parser in
the same file. Keep the corpus at roughly 10 per category: open / close / tap
/ edge.

## Tuning power-model parameters

`firmware/docs/power-model.md` lists the per-source current-draw values. Edit
`Scenario`'s ctor (`test/harness/Scenario.cpp`) to adjust defaults, or use
`s.battery().setCurrentMa("active_summary", 72.0f)` within a scenario.

## Running the suite

```bash
# Full suite
./build/firmware_sim

# Only power-budget
./build/firmware_sim --test-case="power-budget*"

# Only door-filter
./build/firmware_sim --test-case="door-filter*"
```

## Scenario-spec parity

Every scenario in `openspec/specs/device-firmware/spec.md` and
`openspec/specs/device-wake-protocol/spec.md` SHALL have a corresponding
`firmware/test/scenarios/<name>.cpp` test. When firmware spec scenarios are
added, add the test in the same change. This mirrors the discipline already
applied to renderer templates and zone budgets.

## Dry-run against the renderer

Point MockTransport at a live renderer:

```cpp
sim::Scenario s;
s.transport().setLiveHttpBase("http://127.0.0.1:8575");
// HTTP GETs with that prefix are forwarded live; all others use canned responses.
```

Capture the received PNG by copying the last buffer to `firmware/test/out/`:

```cpp
s.display().saveLastTo("firmware/test/out/dry-run-summary.png");
```
