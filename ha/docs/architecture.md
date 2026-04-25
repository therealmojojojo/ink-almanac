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
│   ├─ weather.yaml           MET.no primary (current + hourly) ×2 loc │
│   ├─ weather_forecast.yaml  daily forecast (hi/lo/rain%/5d)       │
│   ├─ weather_nowcast.yaml   MET.no hourly → 1h-6h nowcast label   │
│   ├─ weather_nowcast_minutely.yaml  OWM OneCall 3.0 1-min + combiner │
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
│   (no triplet automation — generated all-at-once, on demand)     │
│   ├─ poetic_weather.yaml    Hourly 21:00–07:00 LLM line          │
│   ├─ low_battery.yaml       <20% → mobile-app notify             │
│   ├─ sleep_strategy.yaml    republish retained helper bundle     │
│   └─ now_playing_override.yaml  Sonos → Now-Playing face         │
│                                                                  │
│  scripts/                                                         │
│   ├─ generate_curated_news.sh      Kottke+AO+Aeon → Claude       │
│   ├─ fetch_rss.sh / fetch_json.sh  feed loaders                  │
│   ├─ generate_news_sensors.py      pre-rsync regen               │
│   ├─ generate_triplets.sh          SSH → Mac host (one-shot)     │
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
│ subscribes        │◄────HTTP────│  - triplet generator (one-shot) │
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
| `news` | state change on `sensor.inkplate_curated_news`; HA start | first 3 items of the attribute list |
| `device` | MQTT trigger on retained `inkplate/state/device`; HA start | `sensor.inkplate_device_battery` + voltage + build |
| `sonos` | track change, via SSH + `renderer/scripts/fetch_sonos_art.sh` | Sonos entity attributes + fetched album art |
| `pairing` (pool) | One-shot, operator-fired via `shell_command.generate_triplets` (SSH → `python3 pairing/corpus_build_triplets_v2.py --apply`) | `corpus/_triplets/*.yaml` on the Mac (rebuilds the rotation pool) |
| `pairing` (today) | Daily 06:00 via `shell_command.publish_today_pairing` (SSH → `python3 pairing/publish_today.py`) | Picks today's triplet by sequence rotation; writes `renderer/inputs/{pairing,news}.json` + companion/gallery/nocturne binaries. Also reads `smart_pill.body` from the summary item's YAML and stages it as `news.json` (the runtime smart-pill source). Rotation anchor in host-local `pairing/_state/triplet_epoch.json`. |

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

## Activation model and deactivation precedence

Two separate rules (see `openspec/changes/revise-tap-override-semantics`).

**Activation** — explicit beats ambient:

- Single tap activates `weather_peek` unconditionally outside quiet hours,
  including during `now_playing`. A 60 s auto-revert returns to whatever was
  active before (Sonos gets its face back if still playing).
- Double tap activates `summary_gallery_toggle` outside quiet hours, except
  during `now_playing` (deliberate asymmetry — see gesture_override.yaml
  header for the rationale).
- Sonos-starts-playing activates `now_playing` outside quiet hours, preempting
  whatever was active.
- Scheduled transitions only publish a new `active_mode` when the active
  override is `schedule` (or `summary_gallery_toggle`, which clears at the
  boundary); higher overrides see their `scheduled_face` helper update but
  the device isn't advanced.

**Deactivation precedence** — on expiry, what do we restore? Highest to lowest:

1. `now_playing` — if `prior_override == now_playing` and Sonos is playing
2. `weather_peek` — if `prior_override == weather_peek` and the expiry is still in the future
3. `summary_gallery_toggle` — if `prior_override == summary_gallery_toggle`
4. `schedule` — default fallthrough, including for unknown / empty `prior`

Encoded once as the unified restore cascade (see below), reused by three
sites: `weather_peek` expiry, `now_playing` linger expiry, and the HA-start
stale-peek cleanup.

**Invariant**: `prior_override` SHALL NEVER equal `active_override`. Re-
triggering the same state (a second tap during an active peek, a double-tap
during an active toggle) refreshes the state's timer/face but leaves `prior`
untouched.

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
- `ha/scripts/generate_triplets.sh` — operator-fired SSH wrapper around `python3 pairing/corpus_build_triplets_v2.py --apply`; regenerates the entire triplet pool in one run (not on a cadence)

### HA state — what HA owns authoritatively

Helpers (in `ha/integrations/helpers.yaml`):

- `input_text.inkplate_active_override` — `schedule | now_playing | weather_peek | summary_gallery_toggle`
- `input_text.inkplate_prior_override` — stash for the deactivation restore cascade (invariant: never equal to active_override)
- `input_text.inkplate_scheduled_face` — the clock-derived face, updated even when overridden
- `input_datetime.inkplate_weather_peek_expires_at` — armed at single-tap; the expiry automation triggers at this wall-clock moment
- `input_datetime.inkplate_sonos_active_{start,end}` — Sonos fast-path window (07:00–20:00 default)
- `input_datetime.inkplate_quiet_{start,end}` — quiet window (00:00–05:00 default)
- `input_number.inkplate_weather_peek_seconds` — 60 default (matches kSummaryTimerSec)
- `input_number.inkplate_linger_seconds` — 90 default
- `input_number.inkplate_fast_path_interval_seconds` — 180 default
- `input_boolean.inkplate_publisher_enabled` — renderer-input publisher master switch
- `timer.inkplate_now_playing_linger` — started on Sonos pause/idle; cancelled if music resumes in-window

### Face-selection state machine (HA)

Activation and deactivation follow different rules — there is no single
priority cascade. Each event type has its own handler, and deactivations
share one restore cascade.

**Activations** (per event):

```
single tap     ──▶  active = weather_peek
                    prior  = <current>  (unless current already weather_peek;
                                         invariant prior != active)
                    arm expiry at now + 60 s
                    suppressed during quiet hours

double tap     ──▶  active = summary_gallery_toggle
                    prior  = <current>  (unless current already toggle)
                    publish the toggled face (summary↔gallery)
                    suppressed during quiet hours
                    suppressed during now_playing
                    no-op when scheduled_face == night

sonos→playing  ──▶  active = now_playing
                    prior  = <current>
                    publish now-playing
                    suppressed during quiet hours (re-evaluated at quiet-end)

schedule boundary  ──▶  scheduled_face advances always
                        active_mode advances + wake only if
                            active_override in {schedule, summary_gallery_toggle}
                        toggle is cleared to schedule on boundary
```

**Deactivations** run the *unified restore cascade*:

```
┌─────────────────────────────────────────────────────┐
│ trigger:                                            │
│   weather_peek expiry                               │
│   now_playing linger-expired (sonos not playing     │
│                               AND still active=now_playing) │
│   HA start + stuck-past-expiry weather_peek         │
└────────────────────────┬────────────────────────────┘
                         ▼
    prior == now_playing AND sonos playing?   ── yes ──▶  restore now_playing
                         │
                         no
                         ▼
    prior == weather_peek AND expiry in future? ─ yes ──▶  restore weather_peek
                         │
                         no
                         ▼
    prior == summary_gallery_toggle?           ── yes ──▶  restore summary_gallery_toggle
                         │
                         no
                         ▼
                   restore schedule
                         │
                         ▼
              set active_override, reset prior_override = schedule
              (cascade consumes prior — without reset, restoring to
              e.g. now_playing would leave prior == active, violating
              the invariant and corrupting the next activation),
              publish retained active_mode, pulse advisory wake
```

**Quiet-hours suppression**: between `quiet_start` and `quiet_end`, tap
gestures are suppressed (ack glyph on-device only) and `now_playing`
activation is suppressed (re-evaluated when quiet-hours end). Suppression
is about the device being deliberately ambient at night, not a priority
rule.

**22:00 schedule boundary with active Now-Playing**: HA advances
`scheduled_face → night` internally but does NOT pulse `wake`. When
music ends and linger elapses, the restore cascade lands on
`scheduled_face == night` → `wake` fires.

**Tap during now_playing linger**: a tap while the 90 s linger timer is
running peeks weather; the linger-expired event later finds
`active_override != now_playing` and is a no-op. If the peek then expires,
its restore cascade asks "is Sonos playing?" — no → fall through to
`schedule`, not back to a phantom now-playing.

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
