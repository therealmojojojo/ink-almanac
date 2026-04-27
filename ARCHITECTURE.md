# Architecture

This document explains the runtime topology, data flow, and the design decisions behind why each piece sits where it does. Source of truth is the code itself — when this doc and the code disagree, the code is right and the doc is stale (please open an issue or fix it).

## Hosts and processes

| Host | Process(es) | Lifecycle |
|---|---|---|
| **Mac** (always-on) | `renderer` (Node + Playwright on port 8575, launched by `~/Library/LaunchAgents/com.inkplate.renderer.plist`) | KeepAlive=true, restarts on crash + at login |
| Mac | `corpus_review.py` (optional, port 8081) | manual |
| Mac | `pairing/publish_today.py` | invoked daily at 06:00 by HA over SSH |
| **HAOS VM** | Home Assistant Core | always-on |
| HAOS VM | Mosquitto MQTT broker (port 1883, add-on) | always-on |
| HAOS VM | Advanced SSH & Web Terminal (port 2222, add-on) | always-on |
| **Inkplate 10** | firmware (`firmware/src/main_loop.cpp`) | one tick per wake, then deep-sleep until the next scheduled wake or IMU interrupt |

The renderer is the only mutable-state service of consequence. Every other component is either stateless (the device, after each wake) or ratcheting toward a daily mode (the corpus/pairing tooling).

## Data flow — daily triplet

```
                                   06:00 EEST
                                       │
                                       ▼
       ┌─────────────────────────────────────────────────────────────┐
       │  HA automation `inkplate_06_00_publish_today_s_triplet`     │
       │  fires shell_command.publish_today_pairing                  │
       └─────────────────────────────────────────────────────────────┘
                                       │ SSH
                                       ▼
       ┌─────────────────────────────────────────────────────────────┐
       │  on the Mac: pairing/publish_today.py                       │
       │  • read corpus/_triplets/*.yaml (sorted by `sequence`)      │
       │  • idx = (today − epoch).days % len(triplets)               │
       │  • compose pairing.json from items[summary, gallery,        │
       │    anchor, aligned_nocturne], copy companion/gallery/       │
       │    nocturne binaries, write smart_pill body to news.json    │
       └─────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
              renderer/inputs/{pairing,news,clock,weather,sonos,device}.json
              renderer/inputs/{companion,gallery,nocturne}.jpg
                                       │
                                       │ read fresh on every render
                                       ▼
       ┌─────────────────────────────────────────────────────────────┐
       │  renderer/src/modes/index.ts:prepareMode(mode)              │
       │  • gather*() loads the relevant inputs                      │
       │  • Zod-parse against schema.ts                              │
       │  • build*Html() emits HTML, dither mask                     │
       │  • Playwright loads HTML, screenshots 1200×825              │
       │  • sharp converts to single-channel 8-bit PNG               │
       └─────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
                      GET /display/:mode.png  →  device
```

## Data flow — minute-by-minute clock and alternation

```
   every minute                                  HA's schedule alternation tick
   (HA `inkplate_publish_clock`)                 (every :00, :15, :30, :45)
            │                                              │
            ▼                                              ▼
   POST /inputs/clock                          compute (tier, parity, offset)
   { "time": "07:42",                          → target face
     "date": "Monday · April 27" }              if changed AND
            │                                       active_override == schedule:
            ▼                                       MQTT publish (retained)
   renderer/inputs/clock.json                       inkplate/command/active_mode
            │
            └──────────  used at next render  ─────────────┘

   Device wake (timer at minute boundary, IMU tap, sonos fast-path)
            │
            ▼
   ┌─────────────────────────────────────────────────────────────┐
   │  fw::tick() in firmware/src/main_loop.cpp                    │
   │                                                              │
   │  • reason = ColdBoot/Timer/IMU/HACommand/SonosFastPath       │
   │  • if Timer: ask wake::planWake(minute_of_day, current_mode) │
   │      → Path::Full | Poll | Partial | PollPartial | Skip     │
   │  • if IMU + tap: showTapAck(), then path=Full                │
   │                                                              │
   │  Full path:                                                  │
   │    WiFi assoc → NTP resync → MQTT connect → publish gesture │
   │    → grace window (2 s subscribed to active_mode)            │
   │    → resolveActiveMode() reads retained payload              │
   │    → HTTP GET /display/:mode.png → drawImage (3-bit)         │
   │    → fetch /display/:mode/clock-zone.json (caches font_size, │
   │      x, y in RTC slow memory)                                │
   │    → post-Full zone cleanup: solid-black + white-with-digits │
   │      partial pulses to neutralize 3-bit AA edges             │
   │    → publish device-state heartbeat                          │
   │                                                              │
   │  Partial path:                                               │
   │    setDisplayMode(OneBit)                                    │
   │    if last_drawn != 0xff:                                    │
   │      clock::draw(preset, last HH:MM) → partialUpdate         │
   │    clock::draw(preset, current HH:MM) → partialUpdate        │
   │    setDisplayMode(ThreeBit)                                  │
   │                                                              │
   │  Skip / Poll: no draw, just MQTT housekeeping or sleep       │
   └─────────────────────────────────────────────────────────────┘
            │
            ▼
   schedule next wake = +N minutes (planner result),
   armed timer + IMU INT1, esp_deep_sleep_start()
```

## Wake-schedule planner

The whole minute-tier system lives in **`firmware/src/wake.cpp`**:

```cpp
constexpr Tier tierFor(int min_of_day) {
  if (min_of_day >= 1320 || min_of_day < 390) return {15,  0, 0, false};  // Night
  if (min_of_day < 600 || min_of_day >= 1020) return {15,  3, 1, false};  // Morning + Evening
  return {30, 0, 5, true};                                                 // Midday
}
```

- **Full** = a multiple of `full_min` (every 15 min Morning/Evening/Night, every 30 min Midday). Fetches PNG, full-screen waveform.
- **Poll** = WiFi+MQTT only, reads retained `active_mode`, no draw.
- **Partial** = no WiFi, offline 1-bit clock-zone refresh.
- **PollPartial** = Midday's combined: poll for mode change, draw if not.
- **Skip** = device is awake briefly to re-arm but does no work.

`planWake(minute_of_day, mode)` returns `(Path, minutes_to_next_non_skip_wake)` so the caller can compute the deep-sleep duration. Tests in `firmware/test/scenarios/schedule_tests.cpp` cover every cadence transition.

## Tap → face change

```
   tap on frame                ~5–20 ms
   IMU INT1 → GPIO 36 LOW      ESP32 ext0 wake
            │
            ▼
   ~200 ms after wake          firmware reads TAP_SRC register,
                               decides Single (bit 5) vs Double (bit 4)
            │
            ▼
   ~450 ms                     showTapAck:
                                 • setDisplayMode(OneBit)
                                 • fillRect halo BLACK   → partialUpdate
                                 • fillRect halo WHITE,  → partialUpdate
                                   1 or 2 dots in BLACK    (badge visible)
                                 • delay(700 ms)
                                 • fillRect halo WHITE   → partialUpdate
                                 • setDisplayMode(ThreeBit)
            │
            ▼
   ~1.5 s                      WiFi assoc starts
   ~3 s                        WiFi up, NTP resync, MQTT connect
                               publish inkplate/state/gesture { "kind": "single|double" }
            │
            ▼
   ~3.2 s                      HA gesture handler:
                                 • flip input_number.inkplate_alternation_offset
                                 • recompute target face from schedule
                                 • publish inkplate/command/active_mode (retained)
            │
            ▼
   ~3.5 s                      device's grace-window subscription receives the new mode
   ~5 s                        HTTP GET /display/:new-mode.png
   ~7 s                        3-bit Full draw + post-Full cleanup
            │
            ▼
   total tap-to-face-change: ~7–9 s
```

The dot badge appears within ~450 ms regardless of whether the network round-trip succeeds, so the operator gets confirmation that the tap registered well before the face change lands.

## Override state machine (Home Assistant)

`ha/automations/` implements a state machine on `input_text.inkplate_active_override`:

```
                schedule
              ↗   │     ↘
   weather_peek  │   now_playing
       (legacy)  │    (Sonos playing)
              ↘   ▼     ↙
              tap (any kind)
                  │
                  ▼
              flip alternation_offset (during schedule)
              OR peek to tier main for 60 s (during now_playing)
              OR no-op (during Night, quiet hours)
```

Precedence: `now_playing > weather_peek > schedule`. Each override has its own restore cascade triggered on expiry.

- **schedule** is the default. The alternation tick (every 15 min) advances the displayed face.
- **now_playing** activates when Sonos transitions to `playing` (outside quiet hours), publishes `active_mode = now-playing`, and lingers for 90 s after Sonos stops in case the operator just paused briefly.
- **weather_peek** is legacy (the dedicated single-tap path that triggered it has been removed). Defensive automations remain to clean up any retained MQTT residue.

## Why these choices

- **Server-side rendering** (Playwright + Chromium) instead of on-device drawing: lets us reuse standard CSS layout, web fonts, dithering, and the entire Chromium text shaper. The device just decodes a PNG. Tradeoff: needs a Mac/Pi running.
- **3-bit grayscale, no palette dither on server**: Inkplate's library does Floyd-Steinberg internally; doing a second server-side pass adds noise. Validated empirically in `openspec/changes/improve-text-crispness/` (now archived).
- **Glyph-baked clock instead of fetched-PNG-each-minute partial**: keeps the partial path offline (no WiFi every minute) and ~6× cheaper in battery. Cost is ~12 KB of flash for the three baked presets and a small alignment headache (the +2 px nudge in `clock_render.cpp:25`).
- **Per-tier face alternation** instead of a fixed schedule: the original 06:30/10:00/22:00 schedule was static; alternation lets the same tier surface both content types over the day without a new gesture.
- **Tap acknowledgment via partial pulse, not via pre-Full overlay** in the rendered PNG: the renderer doesn't know about taps, and we want feedback in <500 ms — too fast to round-trip through HA. Done entirely on-device.
- **NTP resync on every WiFi-up**: ESP32 RTC drifts ~1.7 s/day; once-per-cold-boot resync (the original) accumulated noticeable drift after a few days, so partial-clock timestamps disagreed with the renderer's. Now both sides converge.

## What lives where (cheat sheet)

| Concern | Where to look |
|---|---|
| What face is currently displayed | `input_text.inkplate_active_override` + `inkplate_scheduled_face` in HA |
| Current alternation phase | `input_number.inkplate_alternation_offset` in HA |
| Last persistent device state | RTC slow memory (`firmware/include/wake.h:Persisted`) — current_mode, partial_refresh_count, clock_zone_{x,y,font_size}, last_drawn_{hh,mm} |
| Renderer inputs (live) | `renderer/inputs/*.json` + `*.jpg` |
| Today's triplet | `pairing/_state/triplet_epoch.json` (the day-1 anchor) + `corpus/_triplets/*.yaml` (sorted by sequence) |
| Renderer logs | `/tmp/inkplate-renderer.{out,err}.log` |
| Device logs | `pio device monitor -b 115200` (when USB-tethered) |
| HA logs | `ha core logs` over the SSH add-on |

## Failure modes worth knowing

- **Mac asleep / off** → device gets HTTP errors, draws an 80×80 corner indicator, panel otherwise unchanged. Recovers automatically when Mac wakes.
- **WiFi flaky** → device retries up to `kRendererMaxRetries` (3), then gives up for this wake. Next wake retries fresh.
- **Renderer crashed** → launchd auto-respawns within ~10 s (`KeepAlive: true` + `ThrottleInterval: 10`); the firmware-level retry loop in `server.ts:listenWithRetry` covers TIME_WAIT collisions during respawn.
- **HA not running** → device's last retained `active_mode` keeps it on whatever face was active. Once HA's back, alternation/gestures resume.
- **Corpus misedit** → `corpus validate` exits non-zero and `publish_today.py` won't pick a stale triplet. The previous day's `pairing.json` stays in the renderer.
- **`inkplate_publisher_enabled` toggled off** → all renderer-input HA publishers silently no-op. The renderer keeps serving stale data; the device renders that. There's no automated alarm. (We learned this the hard way.)

## Further reading

- [`SETUP.md`](SETUP.md) — operator quick-start, by host.
- [`firmware/README.md`](firmware/README.md) — firmware deep-dive, host simulator, tests.
- [`renderer/README.md`](renderer/README.md) — endpoints, template structure, input schemas.
- [`ha/README.md`](ha/README.md) — automation flow, override state machine, deploy.
- [`corpus/README.md`](corpus/README.md) + [`pairing/README.md`](pairing/README.md) — content pipeline.
- [`openspec/specs/`](openspec/specs/) — ratified capabilities (corpus schema, taxonomy, triplets).
