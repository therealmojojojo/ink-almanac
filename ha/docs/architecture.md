# HA integration architecture

The HAOS VM is the project's nervous system. Every face's data flows through
HA; every override, transition, and scheduled trigger runs in HA. The device
and the renderer are otherwise stateless.

## Component map

```
┌──────────────────────────────────────────────────────────────────┐
│                         HAOS VM (this Mac)                        │
│                                                                  │
│  integrations/                                                    │
│   ├─ zone_and_astro.yaml    sun, moon, home coords               │
│   ├─ weather.yaml           MET.no primary + OWM fallback ×2 loc │
│   ├─ weather_forecast.yaml  daily forecast (hi/lo/rain%/5d)       │
│   ├─ weather_nowcast.yaml   MET.no hourly → 1h-6h nowcast label   │
│   ├─ weather_nowcast_minutely.yaml  Open-Meteo 15-min + combiner  │
│   ├─ mqtt.yaml              Mosquitto bridge + device-state       │
│   ├─ helpers.yaml           input_text / input_datetime / timer   │
│   ├─ notify.yaml            alias → operator mobile-app notify    │
│   └─ shell_commands.yaml    registered commands                   │
│                                                                  │
│  sensors/                                                         │
│   ├─ weather_template.yaml  renderer-facing fields × 2 locations │
│   ├─ kitchen_climate.yaml   aliased to chosen physical sensor    │
│   ├─ hn.yaml                HN top-5 every 30min                 │
│   ├─ news_sources.yaml      AUTOGEN from config/news_sources.yaml│
│   └─ astro.yaml             sunrise/sunset/moon/astro_event      │
│                                                                  │
│  automations/                                                     │
│   ├─ schedule.yaml          06:30 / 10:00 / 22:00 transitions    │
│   ├─ pairings.yaml          Sun 23:30 → corpus pair generate-week│
│   ├─ poetic_weather.yaml    Hourly 21:00–07:00 LLM line          │
│   ├─ low_battery.yaml       <20% → mobile-app notify             │
│   ├─ sleep_strategy.yaml    republish retained helper bundle     │
│   └─ now_playing_override.yaml  Sonos → Now-Playing face         │
│                                                                  │
│  scripts/                                                         │
│   ├─ fetch_hn_top.sh               curl+python3                  │
│   ├─ fetch_rss.sh / fetch_json.sh  feed loaders                  │
│   ├─ generate_news_sensors.py      pre-rsync regen               │
│   ├─ generate_pairings_week.sh     SSH → Mac host corpus CLI     │
│   └─ generate_poetic_weather_line.sh  Claude / Ollama call       │
│                                                                  │
│  config/                                                          │
│   ├─ news_sources.yaml                                            │
│   ├─ poetic_weather_line.yaml                                     │
│   └─ night_fallback_lines.yaml                                    │
│                                                                  │
│  state/                                                           │
│   └─ poetic_weather.txt     latest line, read by renderer         │
└──────────────────────────────────────────────────────────────────┘
        │ MQTT (Mosquitto)                 │ SSH (deploy + pairings)
        │                                  │
        ▼                                  ▼
┌──────────────────┐              ┌────────────────────────────────┐
│ Inkplate device   │              │ Mac host                        │
│                   │              │  - TS renderer (port 8575)      │
│ subscribes        │◄────HTTP────│  - corpus CLI (pair generate-*) │
│   command/*        │    (wake    │                                 │
│ publishes          │     → fetch │                                 │
│   state/*          │     png)    │                                 │
└──────────────────┘              └────────────────────────────────┘
```

## Data flow per face

| Face | HA produces | Renderer consumes |
|---|---|---|
| Summary | temp/cond/H-L/rain × 2 loc, HN top-5, news_\* top-5, sunrise/sunset, kitchen T/H, device battery | `/display/summary.png` |
| Weather | per-location weather fields, astro (sunrise/sunset/moon/daylight/next-full, astro_event_tonight) | `/display/weather.png` |
| Gallery | (no live HA inputs; reads pairings/ files on the host) | `/display/gallery.png` |
| Night | poetic_weather.txt (from ha/state/ or HTTP) | `/display/night.png` |
| Now-Playing | media_player.kitchen_sonos attributes | `/display/now-playing.png` |

## Input publisher catalog

HA writes each renderer input via `POST /inputs/:name` on the Mac host
(`ha/integrations/rest_commands.yaml` + `ha/automations/publish_inputs.yaml`).
Gated by `input_boolean.inkplate_publisher_enabled` (master kill-switch).

| Input | Trigger(s) | Source |
|---|---|---|
| `clock` | time-pattern every 1 minute + HA start | `now()` |
| `weather` | state change on any weather template sensor; hourly safety; HA start | weather + astro sensors + `sensor.inkplate_poetic_weather_line` |
| `climate` | state change on kitchen temp/humidity; HA start (gated on sensor availability) | `sensor.kitchen_temperature` / `_humidity` |
| `hn` | state change on `sensor.inkplate_hn_top5`; HA start | first 3 items of the attribute list |
| `device` | MQTT trigger on retained `inkplate/state/device`; HA start | `sensor.inkplate_device_battery` + voltage + build |
| `sonos` | track change, via SSH + `renderer/scripts/fetch_sonos_art.sh` | Sonos entity attributes + fetched album art |
| `pairing` | Sunday 23:30, via SSH + `corpus pair generate-week` | pairings directory on the Mac |

Failure handling: HA's `rest_command` does not retry. A connection-refused
or 5xx is logged at `warning` and the next natural trigger re-publishes.
The renderer does not validate input shape at POST time; shape errors
surface at the next `/display/*.png` request as a 400 from Zod.

Authentication: one shared token. HA stores it pre-composed as
`renderer_input_auth_header: "Bearer <token>"`; the renderer reads the
bare token from `RENDERER_INPUT_TOKEN`.

## MQTT topic contract (shared with firmware)

| Topic | Direction | Retained | Producer | Consumer |
|---|---|---|---|---|
| `inkplate/command/active_mode` | HA → device | ✓ | schedule / now_playing_override | firmware (on wake) |
| `inkplate/command/wake` | HA → device |   | every transition | firmware (MQTT wake) |
| `inkplate/command/sleep_strategy` | HA → device | ✓ | sleep_strategy automation | firmware (on wake) |
| `inkplate/state/device` | device → HA | ✓ | firmware | low_battery, mqtt sensors |
| `inkplate/state/gesture` | device → HA |   | firmware | (consumed by add-now-playing-mode) |

## Override precedence

Highest to lowest:

1. `now_playing` — Sonos is playing (latched through a linger window)
2. `weather_peek` — single-tap gesture, 5-minute window, auto-reverts
3. `summary_gallery_toggle` — double-tap gesture, persists until next scheduled transition
4. `schedule` — default

Only `schedule` lets the scheduled-mode transitions wake the device. Higher-
precedence overrides still let HA update `input_text.inkplate_scheduled_face`
so the device returns to the right face when the override lifts.

## State machine — the full HA ⇄ Renderer ⇄ Device lifecycle

The three actors have distinct, non-overlapping roles. HA decides **what**
and **when**. The renderer decides **how it looks**. The device decides
**when to ask**.

### Actor roles

| Actor | Runs on | State | Role |
|---|---|---|---|
| HA | HAOS VM `${HA_HOST}` | Authoritative: override state, scheduled face, sleep-strategy helpers | Computes the active face; publishes retained MQTT; writes renderer input files |
| Renderer | Mac host `${RENDERER_HOST}:8575` | Stateless per request; reads `renderer/inputs/*.json` | Serves `GET /display/{mode}.png` and accepts `POST /inputs/:name` |
| Device | Inkplate 10 ESP32 | RTC-memory only (last-drawn mode, partial-refresh count, last door rotation) | Thin client: wake → resolve mode → fetch → draw → publish state → sleep |

### Channels

**MQTT** (broker on HAOS VM):

| Topic | Dir | Retained | Payload |
|---|---|:-:|---|
| `inkplate/command/active_mode` | HA→device | ✓ | face name |
| `inkplate/command/wake` | HA→device | — | pulse on transitions / kitchen-motion |
| `inkplate/command/sleep_strategy` | HA→device | ✓ | helper bundle (Sonos window, quiet window, fast-path interval) |
| `inkplate/state/device` | device→HA | ✓ | `{voltage, percentage, wake_reason, active_mode, build}` |
| `inkplate/state/gesture` | device→HA | — | `{kind: single \| double}` |

**HTTP** (renderer on LAN):

- `GET /display/{mode}.png` — device and operator-preview consumers
- `POST /inputs/:name` — HA publisher writes (see `add-ha-renderer-input-bridge`)
- `GET /healthz`, `GET /display/:mode/preview`, `GET /dither-test` — ops

**SSH** (HAOS VM → Mac):

- `ha/scripts/fetch_sonos_art.sh` — writes `renderer/inputs/sonos.json` + album art on track change
- `ha/scripts/generate_pairings_week.sh` — writes `pairings/*.json` every Sunday 23:30

### HA state — what HA owns authoritatively

Helpers (in `ha/integrations/helpers.yaml`):

- `input_text.inkplate_active_override` — `schedule | now_playing | weather_peek | summary_gallery_toggle`
- `input_text.inkplate_prior_override` — stash for restoration after higher-precedence lift
- `input_text.inkplate_scheduled_face` — the clock-derived face, updated even when overridden
- `input_datetime.inkplate_sonos_active_{start,end}` — Sonos fast-path window (07:00–20:00 default)
- `input_datetime.inkplate_quiet_{start,end}` — quiet window (00:00–05:00 default)
- `input_number.inkplate_fast_path_interval_seconds` — 180 default
- `input_boolean.inkplate_publisher_enabled` — renderer-input publisher master switch
- `timer.inkplate_now_playing_linger` — 90 s after Sonos pause/idle

### Face-selection state machine (HA)

At every event, HA re-evaluates the active face and republishes retained
`inkplate/command/active_mode`. The resolution is a priority cascade:

```
                  ┌──────────────────────────┐
                  │ event:                   │
                  │  Sonos state change      │
                  │  linger timer expires    │
                  │  gesture received        │
                  │  schedule boundary       │
                  │  HA startup              │
                  └────────────┬─────────────┘
                               ▼
         ┌────────────── Sonos playing OR linger running? ─── yes ──▶  active = now-playing
         │                      │
         │                      no
         │                      ▼
         │          weather_peek window open? ─────────── yes ──▶  active = weather
         │                      │
         │                      no
         │                      ▼
         │          summary_gallery_toggle set? ───────── yes ──▶  active = toggled face
         │                      │
         │                      no
         │                      ▼
         │          active = scheduled_face (by clock)
         └──────────────────────────────────────────────────────▶  publish active_mode
                                                                   pulse wake (if not already
                                                                   on that face OR if HA init)
```

**Activation rule** (any higher precedence overtakes lower): save prior
override, switch `active_override`, republish `active_mode`, pulse `wake`.

**Deactivation rule** (high falls away): if `prior_override` is still
time-valid, restore it; else fall to `schedule`. Republish `active_mode`;
pulse `wake` only if the device isn't already showing the new face.

**Quiet-hours suppression**: between `quiet_start` and `quiet_end`, the
`now_playing` activation branch is forced off. Night remains active even
if music plays.

**22:00 schedule boundary with active Now-Playing**: HA advances
`scheduled_face → night` internally but does NOT pulse `wake`. When
music ends and linger elapses, `wake` fires.

### Device wake loop — one tick of `fw::tick(hal, reason)`

A single wake = a single complete tick. Steps:

```
1. Identify wake reason:
   timer | imu | ha_command | sonos_fast_path | cold_boot | post_ota
   (PIR removed — motion is HA-side now)

2. If reason == imu:
   a. Read 1-second gyroscope burst.
   b. If |ω| > 20°/s OR last_door_rotation < 2 s ago → suppress, goto 9.
   c. Else read TAP_SRC, queue gesture publish.

3. WiFi + MQTT connect (10 s WiFi, 5 s MQTT).
   On failure: fall back to time-of-day schedule; enable corner indicator;
   continue to step 5 with last-known config.

4. Read retained topics:
   - inkplate/command/active_mode → desired
   - inkplate/command/sleep_strategy → helpers

5. Fast-path early-return: if reason == sonos_fast_path AND
   desired == last_drawn_mode → goto 8.

6. Fetch GET /display/{desired}.png (3 retries with back-off).
   On permanent failure: corner indicator, keep current face, goto 8.

7. Refresh policy:
   - desired != last_drawn_mode          → FULL, reset partial count
   - cold_boot | post_ota                 → FULL
   - partial_refresh_count ≥ 30           → FULL (ghost flush), reset
   - else (minute-tick eligible modes)    → PARTIAL, count++
   last_drawn_mode = desired

8. Publish inkplate/state/device (always).
   Publish inkplate/state/gesture if step 2c queued one.

9. Arm wake sources for the current period (see sleep-strategy table
   in the device-firmware spec). sleepFor(next_timer).
```

### Period-driven wake arming

The sleep-strategy table in `device-firmware` is the normative source.
Summary at a glance:

| Period | Hours | Mode | Timer | Fast-path | IMU |
|---|---|---|---|---|---|
| Morning | 06:30–10:00 | Summary | 15m | 3m (from 07:00) | yes |
| Daytime | 10:00–20:00 | Gallery | 60m | 3m | yes |
| Evening | 20:00–22:00 | Gallery | 60m | — | yes |
| Night | 22:00–00:00 | Night | 60m | — | yes |
| Quiet | 00:00–05:00 | Night | 60m | — | yes |
| Pre-dawn | 05:00–06:30 | Night | 60m | — | yes |
| Now-Playing | variable | Now-Playing | 15m | — | yes |

IMU INT is always armed. Motion (IKEA) is HA-side; the device observes
HA-triggered wakes on its next natural wake (timer or fast-path).

### The wake-latency ladder

When HA decides the face must change, how soon does the device see it?

| Trigger | Latency bound |
|---|---|
| Cold boot, OTA reboot | Immediate (device is already in the active cycle) |
| Device is in the middle of a wake cycle | Immediate (same cycle re-fetches) |
| Sonos activation during fast-path window | ≤ 180 s (fast-path default) |
| Schedule boundary or motion during fast-path window | ≤ 180 s |
| Schedule boundary or motion outside fast-path window | ≤ mode timer (15 min Summary, 60 min Gallery/Night) |
| IMU gesture (tap) | Immediate — device already awake |

Note: HA's `wake` pulse is non-retained. It's effectively a UX
optimization; the **retained** `active_mode` topic is what the device
trusts on any wake.

### Failure modes and their handling

| Failure | Who handles | Behavior |
|---|---|---|
| Renderer down | Device | Corner indicator; 30s/1m/5m/15m/30m back-off; last face persists |
| HA/MQTT down | Device | Fall back to time-of-day schedule; same indicator; retry each wake |
| Renderer POST fails | HA publisher | Log warning, no retry; next natural trigger republishes |
| Sonos art fetch fails | HA script + renderer | JSON still written; spec'd `--faint` + SONOS fallback renders |
| LLM fails for poetic line | HA script | Hand-curated fallback line from `night_fallback_lines.yaml` |
| Verse overflows zone | Renderer | 422 naming the zone; pairing pipeline retries with a shorter selection |
| Renderer input absent (non-device) | Renderer | 503 naming the file; device treats as unreachable |
| `device.json` absent | Renderer | 200 with em-dash battery indicator (graceful degradation) |
| Ghost buildup | Device | Every 30th partial refresh promotes to full; counter resets on mode change |
| Door rotation + tap confusion | Device | Gyroscope door filter suppresses tap for 2 s post-rotation |

### One-line summary

HA owns **when and why**; the renderer owns **how it looks**; the device
owns **when to ask**. The connective tissue is a single retained MQTT
topic (`active_mode`) that survives any failure, plus idempotent HTTP
fetches. Every override, every failure, every boundary recomputes what
`active_mode` should be and republishes it, so the device never has to
reason about policy — it just asks on its own schedule.
