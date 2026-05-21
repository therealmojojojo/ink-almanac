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
│   └─ astro.yaml             sunrise/sunset/moon/astro_event      │
│                                                                  │
│  automations/                                                     │
│   ├─ schedule.yaml          per-tier 3:1 main:weather alternation │
│   ├─ gesture_override.yaml  tap handler (flip / first-wake / peek)│
│   ├─ now_playing_override.yaml  Sonos → Now-Playing face          │
│   ├─ publish_active_override.yaml  mirror override to MQTT        │
│   ├─ publish_wake_schedule.yaml  validate + push wake_schedule    │
│   ├─ publish_inputs.yaml    clock / weather / climate / sonos /   │
│   │                         device REST publishers                │
│   ├─ publish_today_pairing.yaml  06:00 SSH → publish_today.py     │
│   ├─ sleep_strategy.yaml    republish retained helper bundle      │
│   ├─ kitchen_motion_{wake,battery}.yaml  Zigbee PIR → wake / batt │
│   ├─ epd_pwrgood.yaml       low-pwrgood alert from device JSON    │
│   ├─ astro_event.yaml       precompute tonight's astro line       │
│   ├─ poetic_weather.yaml    Hourly LLM line (21:00–07:00)         │
│   ├─ low_battery.yaml       <20% → mobile-app notify              │
│   └─ sonos_remote.yaml      Z2M button → media controls           │
│                                                                  │
│  scripts/                                                         │
│   ├─ publish_today_pairing.sh      SSH → publish_today.py (06:00) │
│   ├─ generate_triplets.sh          SSH → triplet build (one-shot) │
│   ├─ fetch_sonos_art.sh            (legacy; live path is REST)    │
│   ├─ purge_stale_sonos_art.sh      daily cache prune              │
│   ├─ generate_astro_event.{py,sh}  tonight's astronomy line       │
│   ├─ generate_poetic_weather_line.sh  Claude / Ollama call        │
│   └─ validate_wake_schedule.py     used by publish_wake_schedule  │
│                                                                  │
│  config/                                                          │
│   ├─ wake_schedule.yaml     operator-editable per-tier cadences   │
│   ├─ poetic_weather_line.yaml                                     │
│   ├─ night_fallback_lines.yaml                                    │
│   └─ now_playing_sources.yaml                                     │
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
| Summary | temp/cond/H-L/rain × 2 loc, sunrise/sunset, kitchen T/H, device battery; smart-pill body is pre-baked into the triplet sidecar | `/display/summary.png` |
| Weather | per-location weather fields, astro (sunrise/sunset/moon/daylight/next-full, astro_event_tonight) | `/display/weather.png` |
| Gallery | (no live HA inputs; reads pairings/ files on the host) | `/display/gallery.png` |
| Night | `sensor.inkplate_poetic_weather_line` (LLM-or-fallback) | `/display/night.png` |
| Now-Playing | media_player.kitchen_sonos attributes (incl. `media_content_id`); renderer enriches via Spotify+MusicBrainz for the classical layout | `/display/now-playing.png` |

## Input publisher catalog

HA writes each renderer input via `POST /inputs/:name` on the Mac host
(`ha/integrations/rest_commands.yaml` + `ha/automations/publish_inputs.yaml`).
Gated by `input_boolean.inkplate_publisher_enabled` (master kill-switch).

| Input | Trigger(s) | Source |
|---|---|---|
| `clock` | time-pattern every 1 minute + HA start | `now()` |
| `weather` | state change on any weather template sensor; hourly safety; HA start | weather + astro sensors + `sensor.inkplate_poetic_weather_line` |
| `climate` | state change on kitchen temp/humidity; HA start (gated on sensor availability) | `sensor.kitchen_temperature` / `_humidity` |
| `device` | MQTT trigger on retained `inkplate/state/device`; HA start | battery percentage + voltage + build + wifi_rssi + epd_pwrgood |
| `sonos` | state / `media_content_id` change on `media_player.kitchen_sonos`; HA start | Sonos entity attributes (title, artist, album, `media_content_id`, `source_indicator`, `art_url` via `/ha-proxy` same-origin route). The renderer enriches via Spotify+MusicBrainz when a `media_content_id` is present. |
| `pairing` (pool) | One-shot, operator-fired via `shell_command.generate_triplets` (SSH → triplet builder) | `corpus/_triplets/*.yaml` on the Mac (rebuilds the rotation pool) |
| `pairing` (today) | Daily 06:00 via `shell_command.publish_today_pairing` (SSH → `python3 pairing/publish_today.py`) | Picks today's triplet by sequence rotation; writes `renderer/inputs/{pairing,smart_pill}.json` + companion/gallery/nocturne binaries. The smart-pill body is read from the summary item's YAML sidecar (`summary.smart_pill.body`) and staged as `smart_pill.json` — deterministic per-day, no runtime LLM regen. |

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
| `inkplate/command/active_mode` | HA → device | ✓ | schedule / now_playing_override / gesture handlers | firmware (on wake) |
| `inkplate/command/gesture_response` | HA → device |   | gesture handlers | firmware (IMU grace window only) |
| `inkplate/command/wake` | HA → device |   | every transition | firmware (MQTT wake) |
| `inkplate/command/sleep_strategy` | HA → device | ✓ | sleep_strategy automation | firmware (on wake) |
| `inkplate/command/schedule` | HA → device | ✓ | publish_wake_schedule (validated from `ha/config/wake_schedule.yaml`) | firmware (on wake) |
| `inkplate/state/device` | device → HA | ✓ | firmware | low_battery, epd_pwrgood, mqtt sensors |
| `inkplate/state/active_override` | HA → broker | ✓ | publish_active_override (mirrors `input_text`) | firmware (per-minute NowPlaying Poll gate) |
| `inkplate/state/now_playing_track` | HA → broker | ✓ | now_playing_override on track change | firmware (NowPlaying Poll mode-change detection) |
| `inkplate/state/gesture` | device → HA |   | firmware | gesture_override (HA-side tap handler) |

`gesture_response` is the event-channel counterpart of the state-channel
`active_mode`. The IMU grace window in firmware listens on `gesture_response`
specifically so the broker has nothing to replay on subscribe — without that,
the wait would short-circuit on the previously retained `active_mode` (which
encodes the *current* mode, not HA's response to the just-fired tap). HA
publishes both in the gesture-handler actions: `gesture_response` so the
in-flight wake renders the flipped face, `active_mode` so subsequent Full
wakes keep rendering it until the schedule alternation overrides.

## Activation model and deactivation precedence

Two separate rules (origin: `openspec/changes/archive/2026-04-27-revise-tap-override-semantics`; later refined by `2026-05-09-fix-tap-during-now-playing-first-wake` and the per-tier alternation engine).

**Activation** — explicit beats ambient. Both single and double tap drive the same handlers (the toothpick-and-tape frame mount can latch either depending on tap force; distinguishing them would force the operator to calibrate, so HA treats both as the same intent):

- **Tap during schedule** (outside Night, outside quiet hours): flip the *currently-displayed* face to its counterpart and publish (`active_mode = <flip>`, retained, plus `gesture_response = <flip>` non-retained for the firmware's IMU grace window). The flip is read from `sensor.inkplate_commanded_face` (a mirror of the device's last-drawn face) rather than recomputed from the schedule, so repeat taps in the same slot toggle visibly. `active_override` is NOT touched; the next /15 schedule tick republishes the schedule's a priori target, overwriting the tap-driven flip — so a tap is a transient peek lasting up to one Full interval.
- **Tap during now_playing**, branched on `sensor.inkplate_commanded_face`:
  - **First-wake** (mirror ≠ `now-playing`): publish `gesture_response = now-playing` (non-retained). `active_mode` already retains `now-playing` from the Sonos-started automation — no republish needed. Use case: the wake pulse from Sonos-started was lost while the device was deep-asleep, and the operator taps to wake the device into the session.
  - **Peek** (mirror = `now-playing`): publish `gesture_response = weather` and `active_mode = weather` retained, hold 60 s, then republish `active_mode = now-playing`. Lets the operator glance at weather without leaving the music session.
- **Tap during Night or quiet hours**: suppressed (acknowledged on-device by the tap-ack dot but no face change).
- **Sonos → playing** activates `now_playing` outside quiet hours, preempting whatever was active.
- **Schedule boundary**: `scheduled_face` advances always; `active_mode` advances + wake fires only if `active_override == schedule`. Higher overrides see `scheduled_face` advance silently so restore-on-expiry lands on the right phase.

**Deactivation precedence** — on expiry, what do we restore? Highest to lowest:

1. `now_playing` — if `prior_override == now_playing` and Sonos is playing
2. `weather_peek` — if `prior_override == weather_peek` and the expiry is still in the future *(legacy / defensive; no current automation creates `weather_peek`, but the restore cascade still honors a stale retained value)*
3. `summary_gallery_toggle` — if `prior_override == summary_gallery_toggle` *(legacy / defensive, same reason)*
4. `schedule` — default fallthrough

Encoded once as the unified restore cascade, reused by three sites: `weather_peek` expiry (defensive), `now_playing` linger expiry, and the HA-start stale-peek cleanup.

**Invariant**: `prior_override` SHALL NEVER equal `active_override`.

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
| `inkplate/command/gesture_response` | HA→device | — | face name (event channel for IMU grace window) |
| `inkplate/command/wake` | HA→device | — | pulse on transitions / kitchen-motion |
| `inkplate/command/sleep_strategy` | HA→device | ✓ | helper bundle (Sonos window, quiet window, fast-path interval) |
| `inkplate/command/schedule` | HA→device | ✓ | validated wake-schedule JSON (per-tier `full_min` / `poll_min` / `partial_min`) |
| `inkplate/state/device` | device→HA | ✓ | `{voltage, percentage, wake_reason, active_mode, build, epd_pwrgood, wifi_rssi, schedule_hash, diag}` |
| `inkplate/state/active_override` | HA→broker | ✓ | mirror of `input_text.inkplate_active_override` — gates per-minute NowPlaying Poll |
| `inkplate/state/now_playing_track` | HA→broker | ✓ | current `media_content_id` for the NowPlaying Poll mode-change check |
| `inkplate/state/gesture` | device→HA | — | `{kind: single \| double}` |

**HTTP** (renderer on LAN):

- `GET /display/{mode}.png` — device and operator-preview consumers
- `POST /inputs/:name` — HA publisher writes (see `add-ha-renderer-input-bridge`)
- `GET /healthz`, `GET /display/:mode/preview`, `GET /dither-test` — ops

**SSH** (HAOS VM → Mac):

- `ha/scripts/publish_today_pairing.sh` — fired daily at 06:00; runs `python3 pairing/publish_today.py` on the Mac to stage the day's triplet inputs.
- `ha/scripts/generate_triplets.sh` — operator-fired SSH wrapper around the triplet builder; regenerates the entire rotation pool in one run (not on a cadence).
- `ha/scripts/fetch_sonos_art.sh` — legacy; the live Sonos input path is HA → renderer REST POST in `publish_inputs.yaml`.

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

**Activations** (per event — single and double tap behave the same):

```
tap, active=schedule       ──▶  flip displayed face (Weather ↔ tier_main)
(outside Night, outside        publish active_mode = <flip> retained
 quiet hours)                  publish gesture_response = <flip> non-retained
                               active_override UNCHANGED
                               next /15 tick republishes schedule's target

tap, active=now_playing,   ──▶  publish gesture_response = now-playing
 mirror != now-playing         (first-wake; firmware draws now-playing)
 (outside Night/quiet)

tap, active=now_playing,   ──▶  publish gesture_response = weather +
 mirror == now-playing         active_mode = weather retained, hold 60 s,
 (outside Night/quiet)         then republish active_mode = now-playing
                               (peek)

tap during Night or        ──▶  suppressed (tap-ack dot only)
 quiet hours

sonos→playing              ──▶  active = now_playing, prior = <current>
                               publish active_mode = now-playing retained
                               suppressed during quiet hours
                               (re-evaluated at quiet-end and HA start)

schedule boundary          ──▶  scheduled_face advances always
                               active_mode advances + wake only if
                                   active_override == schedule
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
running enters the first-wake-vs-peek branch (override is still
`now_playing`). If music has genuinely stopped, the linger-expired event
later fires the restore cascade — which asks "is Sonos playing?" — no →
fall through to `schedule`, not back to a phantom now-playing.

### Device wake loop — one tick of `fw::tick(hal, reason)`

A single wake = a single complete tick. Steps:

```
1. Identify wake reason:
   timer | imu | ha_command | cold_boot | post_ota
   (PIR removed — motion is HA-side now)

2. If reason == imu:
   a. Read 1-second gyroscope burst (door-rotation suppression).
   b. If |ω| > 20°/s → suppress, goto 9.
   c. Else read TAP_SRC; if a valid tap, paint the tap-ack dot and
      queue a gesture publish.

3. Plan path (schedule planner, src/wake.cpp):
   Full | Poll | Partial | Skip — per the retained schedule
   (inkplate/command/schedule) with the NowPlaying override (per-minute
   Poll while inkplate/state/active_override == now_playing). IMU and
   cold_boot/post_ota force Full.

4. If Partial: render the clock zone offline (no network); goto 9.

5. WiFi + MQTT connect (10 s WiFi, 5 s MQTT).
   On failure: keep the prior-drawn face (no time-of-day invention —
   see fix-active-mode-fallback); enable corner indicator; goto 9.

6. Read retained topics:
   - inkplate/command/active_mode    → desired face
   - inkplate/command/schedule       → wake-schedule
   - inkplate/command/sleep_strategy → helper bundle
   - inkplate/state/active_override  → NowPlaying-Poll gate
   - inkplate/state/now_playing_track → mode-change check (Poll only)

7. If Poll AND no mode-change AND no track-change: publish heartbeat,
   goto 9 (Poll → no Full, no fetch).

8. Otherwise (Full or Poll-promoting-to-Full):
   - Fetch GET /display/{desired}.png (with retries + corner-indicator
     on permanent failure).
   - Refresh: 3-bit Full; periodic partial-counter reset; clock-zone
     post-Full cleanup.
   - Publish inkplate/state/device (heartbeat).

9. Arm wake sources for the current tier (per the wake schedule).
   sleepFor(next minute boundary at Full/Poll/Partial cadence).
```

### Period-driven wake arming

The wake schedule is **operator-pushable** — edit `ha/config/wake_schedule.yaml`, deploy, and HA validates (via `ha/scripts/validate_wake_schedule.py`) and republishes the result to retained MQTT `inkplate/command/schedule`. The firmware reads it on the next wake. Per-tier fields:

- `start` — local-time tier boundary
- `full_min` — Full-refresh cadence (WiFi + MQTT + fetch + 3-bit refresh)
- `poll_min` — Poll cadence (WiFi + MQTT mode-change check; promotes to Full on change). `0` = no separate poll.
- `partial_min` — Partial-refresh cadence (offline; clock zone only). `0` = no partials.

A typical configuration: Morning `15/0/1`, Midday `30/0/10`, Evening `30/0/5`, Night `60/0/15`. See `wake_schedule.yaml` for the live values and the file's header comment for editing rules.

**NowPlaying override**: while `inkplate/state/active_override = now_playing`, the firmware ignores the tier's `poll_min` and runs a fixed per-minute Poll (with the same Full-promote-on-change rule). The override mirror is published by `publish_active_override.yaml` and the track-id by `now_playing_override.yaml` on every track change. See `openspec/changes/archive/2026-05-05-optimise-now-playing-cadence`.

IMU INT is always armed. Motion (IKEA Zigbee PIR) drives HA-side wake pulses; the device picks them up on its next natural wake.

### The wake-latency ladder

When HA decides the face must change, how soon does the device see it?

| Trigger | Latency bound |
|---|---|
| Cold boot, OTA reboot | Immediate (device is already in the active cycle) |
| Device is in the middle of a wake cycle | Immediate (same cycle re-fetches) |
| Sonos track change during an active NowPlaying session | ≤ 60 s (per-minute Poll while `active_override == now_playing`) |
| Schedule boundary, NowPlaying activation, or motion | ≤ `poll_min` if defined for the current tier, else ≤ `full_min` |
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
| Sonos art fetch fails | Renderer | `/ha-proxy/*` shells to curl with a short fast-fail; renderer falls back to `templates/now-playing/fallback.jpg` at render time |
| Spotify or MusicBrainz unreachable | Renderer | Enrichment pipeline is skipped; Now-Playing falls back to the non-classical layout with the publisher's flat title/artist/album fields |
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
