# Inkplate firmware

ESP32 firmware for the Inkplate 10 e-ink panel. Wakes from deep sleep on a
schedule (or an IMU tap), fetches a PNG from the renderer, draws, sleeps.
Partial-refreshes the clock zone every minute without going through the
network.

## What's here

- **Schedule planner** (`src/wake.cpp`) — pure-arithmetic decision over the
  minute-of-day for what kind of wake to do (Full / Poll / Partial /
  PollPartial / Skip). Tier table:

  | Tier | Hours | Full cadence | Partial cadence |
  |---|---|---|---|
  | Night | 22:00 – 06:30 | 15 min | — |
  | Morning | 06:30 – 10:00 | 15 min | 1 min |
  | Midday | 10:00 – 17:00 | 30 min | 5 min (PollPartial) |
  | Evening | 17:00 – 22:00 | 15 min | 1 min |

- **Partial-refresh clock** (`src/clock_render.cpp` + `src/generated/clock_glyphs.{h,cpp}`)
  — composes "HH:MM" from baked Fraunces glyphs into the panel's 1-bit
  framebuffer at the renderer-published clock-zone coordinates. Three
  presets baked: 160u (Summary), 44u (Weather + gallery-landscape), 28u
  (gallery-split + now-playing + gallery-text). Drives the panel via
  `partialUpdate(_forced=true)` to bypass Soldered's `_blockPartial` guard.

- **Post-Full zone cleanup** (`src/main_loop.cpp:doFull`) — after each Full,
  pulses the clock zone solid black then white-with-digits in 1-bit mode.
  Neutralizes the prior 3-bit Full's anti-aliased gray edges so subsequent
  partials diff cleanly without ghosting.

- **Tap acknowledgment** (`src/main_loop.cpp:showTapAck`) — on every IMU
  wake with a confirmed tap, paints a small white-halo badge with 1 dot
  (single tap) or 2 dots (double tap) just left of the battery indicator,
  clears it ~700 ms later. Three partial pulses, ~1.5 s of added wake
  latency. Gives the operator instant feedback that the tap registered.

- **Renderer-published clock zone** — fetched from
  `/display/:mode/clock-zone.json` after every Full and cached in RTC slow
  memory. Lets the partial path place its glyphs at the same pixels the
  Full painted regardless of which face/variant rendered.

- **NTP re-sync on every WiFi-up** — was once-per-cold-boot, RTC drifted
  ~1.7 s/day. Now SNTP fires on every reconnect, with a 600 ms wait so the
  response lands before this wake's render uses it.

- **Spurious-wake guard** — if `TAP_SRC` reads zero on an ext0 wake, the
  firmware re-sleeps without doing any work. Defends against the IMU
  emitting INT1 pulses that don't latch a tap event (observed during
  device-side noise).

- **Host simulator** — same source compiles for the Mac via `cmake`,
  driven by `doctest` scenarios in `test/scenarios/`. Covers schedule
  planner, render path, partial composition, gesture handling — anything
  not directly tied to e-ink waveforms or WiFi/MQTT brokers.

## Directory layout

```
firmware/
├── include/                       public headers
│   ├── hal/                       interface declarations (IDisplay, IIMU, ...)
│   ├── generated/                 (declared in src/generated/)
│   ├── clock_render.h             clock-zone composer
│   ├── config.h                   tunables (tier cadences, tap thresholds, NTP)
│   ├── modes.h wake.h gestures.h battery.h
│   ├── firmware.h                 fw::tick(HAL, Reason) entry
│   └── secrets.h.example
├── src/
│   ├── battery.cpp gestures.cpp modes.cpp wake.cpp
│   ├── main_loop.cpp              the tick orchestrator
│   ├── main.cpp                   on-device entry (ARDUINO-guarded)
│   ├── clock_render.cpp           glyph composer
│   ├── generated/clock_glyphs.{h,cpp}  baked Fraunces presets (auto-gen)
│   └── hal/real/                  Inkplate library wrappers (ARDUINO-guarded)
├── test/                          host simulator
│   ├── hal/mock/                  mocks
│   ├── harness/                   Scenario + MockBattery + power-budget sim
│   ├── scenarios/                 doctest cases (49 currently passing)
│   └── power/                     42-day power-budget assertion
├── docs/                          deep-dives — config, gestures, wake protocol
├── CMakeLists.txt                 host build
└── platformio.ini                 esp32 build
```

## Building / flashing

```sh
# Host simulator (run on your dev machine, no hardware needed)
cmake -B build_host -S . && cmake --build build_host && ./build_host/firmware_sim

# Real device
cp include/secrets.h.example include/secrets.h
# edit secrets.h with WiFi / MQTT / RENDERER_BASE
pio run -e inkplate10 --target upload
pio device monitor -b 115200
```

OTA isn't wired (PlatformIO's OTA upload requires the device to be awake,
which it isn't between wakes). All updates are USB.

## How a wake looks (Full path)

```
detect wake reason  → wake::Reason{ColdBoot,Timer,IMU,...}
read IMU tap        → gestures::TapKind{None,Single,Double}
showTapAck (if IMU + tap)
plan path           → wake::planWake(minute_of_day, current_mode)
                    → Path{Full,Poll,Partial,PollPartial,Skip}
                      (non-Timer reasons all force Full)

WiFi connect (timeout 10 s) → ensureTimeSynced (SNTP, 600 ms)
MQTT connect → publish gesture (if IMU + tap)
            → grace window: subscribe to active_mode for 2 s

resolve active_mode (retained MQTT, fallback to time-of-day)
draw URL/PNG → drawImageFromUrl(/display/<mode>.png, full=true)
fetchAndStoreClockZone(/display/<mode>/clock-zone.json)
post-Full zone cleanup: 2× partialUpdate1Bit
publish device-state heartbeat

schedule next wake = next non-Skip minute per planner
deep sleep
```

The Partial path is much shorter:

```
setDisplayMode(OneBit)
if last_drawn != 0xff: clock::draw(last HH:MM); partialUpdate1Bit  // seed
clock::draw(current HH:MM); partialUpdate1Bit                       // diff cleans + draws
setDisplayMode(ThreeBit)
last_drawn = current HH:MM
schedule next wake; deep sleep
```

`Partial` falls through to `Full` if the active mode's font_size has no
baked preset (so far this only happens if the renderer publishes a
clock-zone we don't recognize). Night and Now-Playing skip partial entirely
— they don't have a single clock element the renderer can publish.

## How a tap looks

| T | Action | Visible |
|---|---|---|
| 0 ms | tap → INT1 → ESP32 ext0 wake | — |
| ~200 ms | read TAP_SRC, decide Single (bit 5) / Double (bit 4) | — |
| ~250–500 ms | Pulse 1: fill halo black, partialUpdate | brief black square |
| ~500–750 ms | Pulse 2: fill halo white, dots black, partialUpdate | white badge with 1 or 2 black dots |
| ~750–1450 ms | delay(700) | dots stay |
| ~1450–1700 ms | Pulse 3: fill halo white, partialUpdate | dots clear |
| ~1700 ms | continue with WiFi connect → fetch → Full → post-Full cleanup | — |
| ~7–9 s | new face painted | new content |

Battery cost: 3 partial pulses ≈ 0.18 mAh per tap. On a 5000 mAh pack a
tap costs ~0.0036 % of capacity.

## Tunables (`include/config.h`)

| Constant | Value | Purpose |
|---|---|---|
| `kTzOffsetSec` | 3 × 3600 | local time offset from UTC. Fixed compile-time; no DST. |
| `kTapThreshold` | 1 | LSM6DSO tap threshold in 1/32 g (≈62.5 mg). Lowered for the wire-tied frame mount. |
| `kTapDurationMs` | 40 | LSM6DSO shock duration cap. |
| `kDoubleTapWindowMs` | 350 | LSM6DSO double-tap timing window. |
| `kGestureGraceMs` | 2000 | how long the firmware waits for HA's `active_mode` reply after publishing a gesture. |
| `kRendererMaxRetries` | 3 | HTTP fetch retries before drawing the corner-indicator. |
| `kSummaryTimerSec` / `kWeatherTimerSec` / etc. | mode-specific | wake intervals per mode (largely deprecated by the schedule planner). |

## Debugging

Every Full / Poll / PollPartial wake publishes `inkplate/state/device` with
`{voltage, percentage, wake_reason, active_mode, build}`. Watch via:

```sh
mosquitto_sub -h <mqtt-host> -u inkplate -P <pwd> -t 'inkplate/state/#' -v
```

Per-tick serial output (USB-tethered): `[tick] path=...`, `[partial] mode=...`,
`[ntp] time=...`, `[IMU] drain: TAP_SRC=...`. Set `pio device monitor -b 115200`.

## Tests

```sh
cmake --build build_host && ./build_host/firmware_sim
# 49 scenarios pass: schedule cadences, partial promotion, post-Full cleanup,
# tap-ack pulse counts, mode-change Full promotion, Sonos fast-path, etc.
```

The `test/power/power_budget.cpp` scenario asserts the device is ≥20%
battery at simulated day 42 against a placeholder current-draw model
in `test/harness/Scenario.cpp`. Update those numbers after a real
power-profiler measurement.

## Further reading

- [`docs/config.md`](docs/config.md) — every tunable, justified.
- [`docs/wake-protocol.md`](docs/wake-protocol.md) — MQTT topics, wake-reason semantics.
- [`docs/gestures.md`](docs/gestures.md) — tap detection chain.
- [`docs/power-budget.md`](docs/power-budget.md) + [`docs/power-model.md`](docs/power-model.md) — battery math.
- [`../ARCHITECTURE.md`](../ARCHITECTURE.md) — system-level diagram.
