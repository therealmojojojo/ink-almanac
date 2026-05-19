# ha/ — Home Assistant configuration

Source of truth for the HA side. Deployed to the HAOS VM as
`/config/custom/inkplate/` by `ha/deploy.sh`. Drives:

- The per-tier face alternation engine (15 / 30 / 15 / static-Night).
- Tap → flip alternation phase, or peek-to-main during Now-Playing.
- Sonos override (now-playing activate, linger, restore-prior).
- Renderer-input publishers (clock, weather, sonos, device, plus the
  daily triplet trigger that runs `pairing/publish_today.py` over SSH).
- Sensor pipelines feeding renderer inputs (forecast, astro events, the
  poetic weather line LLM job).

## Layout

```
ha/
├── automations/         YAML automations (schedule, gestures, publishers,
│                        now-playing, sonos remote, weather peek, ...)
├── sensors/             template / rest / scrape sensors
├── scripts/             helper scripts invoked via shell_command
│                        (LLM line generators, pairing runner)
├── config/              operator-editable lists (poetic_weather, news_sources,
│                        night_fallback_lines, now_playing_sources)
├── integrations/        included from configuration.yaml — helpers,
│                        rest_commands, shell_commands, command_line_sensors,
│                        weather_forecast template
├── state/               runtime state files (poetic_weather.txt, astro_event.txt,
│                        curated_news.json) — gitignored
├── docs/                architecture, deploy, troubleshooting, sleep-strategy
├── deploy.sh            rsync + ha core check + restart over SSH
├── secrets.yaml.example copy to secrets.yaml, fill in, never commit
└── README.md
```

## Override state machine

`input_text.inkplate_active_override` controls what gets published to
`inkplate/command/active_mode`. Values, in precedence order (highest first):

| Value | Set by | Cleared by |
|---|---|---|
| `now_playing` | Sonos transitions to playing (outside quiet hours) | linger expiry after Sonos stops, or another override taking over |
| `weather_peek` | (legacy — no automation creates this any more) | the dedicated 5-min expiry timer or the HA-start cleanup; defensive code paths still honor it for retained MQTT residue |
| `schedule` | the alternation tick at every 15 min | — |

When `active_override == schedule`, the alternation tick publishes the
current target face every 15 min:

```
parity = (((minute_of_day - tier_start) // tier_full) + alternation_offset) % 4
target = parity == 0 ? 'weather' : tier_main
```

3:1 main:weather cycle — weather lands on slot 0 of each tier (the slot
aligned to `tier_start`), main fills the other three. Concretely: weather
appears at 06:30 / 07:30 / 08:30 / 09:30 in Morning, at 10:00 / 12:00 /
14:00 / 16:00 in Midday, and at 17:00 / 18:00 / 19:00 / 20:00 / 21:00 in
Evening.

| Tier | Hours | tier_full | tier_main |
|---|---|---|---|
| Morning | 06:30–10:00 | 15 min | summary |
| Midday | 10:00–17:00 | 30 min | gallery |
| Evening | 17:00–22:00 | 15 min | gallery |
| Night | 22:00–06:30 | n/a | night (no alternation) |

When `active_override == now_playing`, the tick still recomputes
`scheduled_face` so override-restore lands on the right phase, but does
not publish active_mode.

## Tap handler

`automations/gesture_override.yaml` listens on `inkplate/state/gesture` and
treats `single` and `double` as the same intent (the wire-tied frame
mount can latch either depending on tap force; distinguishing them
forces the operator to calibrate tap force). Two automations:

- **Tap during schedule** → flip the currently-displayed face to its
  counterpart and publish. Reads the displayed face from
  `sensor.inkplate_commanded_face` (an MQTT-mirror of the `active_mode`
  field in `inkplate/state/device` — i.e. the face the device last
  actually rendered, not the last face HA commanded) so repeat-taps in
  the same slot toggle back and forth visibly. Does NOT touch
  `inkplate_alternation_offset` or `inkplate_scheduled_face` — the next
  /15 tick recomputes from the untouched offset and restores the
  schedule's a priori target, regardless of what the tap produced.
  Effectively a transient toggle lasting up to one Full interval
  (15 min Morning/Evening, 30 min Midday) before the schedule resumes.
- **Tap during now_playing** → split on the displayed face (mirror sensor):
  - **First-wake tap** (mirror != `now-playing`): publish
    `gesture_response = now-playing` (non-retained). The screen wasn't
    on now-playing yet — typically because the wake pulse from the
    Sonos-started automation was lost while the device was deep-asleep.
    This first tap is the operator's way of waking the device into the
    now-playing session; the firmware's IMU grace window picks up the
    response and draws now-playing.
  - **Subsequent peek** (mirror == `now-playing`): publish
    `active_mode = weather` retained, hold for 60 s, then publish
    `active_mode = now-playing` to revert. Lets the operator glance at
    the weather without leaving the music session. A tap during the
    peek window lands in the first-wake branch (mirror is now `weather`)
    and snaps back to now-playing — i.e., tap to peek, tap again to
    come back.

Both are no-ops during Night (no alternation) and during quiet hours.

## Renderer-input publishers

`automations/publish_inputs.yaml` keeps `renderer/inputs/*.json` in sync
with HA's view of the world. Five publishers, all gated on
`input_boolean.inkplate_publisher_enabled`:

| Topic | Trigger | What it writes |
|---|---|---|
| clock | every minute + HA start | `time` ("HH:MM") + `date` ("Monday · April 27") |
| weather | weather sensor state-change + hourly + HA start | locations × {current, forecast, nowcast}, poetic line, astro |
| sonos | media_player.kitchen_sonos state / content_id change + HA start | state, title, artist, album, source_indicator, art_url, media_content_id — only when actually playing AND has metadata (defensive: empty transients no longer overwrite the file). The renderer uses `media_content_id` (Spotify track id) to enrich the input with composer / work / performers / year for the classical Now-Playing layout. |
| device | MQTT message on `inkplate/state/device` + HA start | battery percentage + voltage + build, last_seen |

The daily triplet — `pairing/publish_today.py` over SSH at 06:00 — writes
`pairing.json`, `companion.jpg`, `gallery.jpg`, `nocturne.jpg`, and
`news.json` (the smart-pill body) directly via filesystem on the
renderer host. It does NOT go through the HA REST publisher.

Smart-pill content is **deterministic per-day**: read from the summary
item's YAML sidecar field `summary.smart_pill.body`. The earlier live
Claude regen pipeline was removed because it produced different prose
on every HA restart. If you need a fresh gloss for a new corpus item,
generate it offline at corpus-build time, not at runtime.

## Sonos remote (IKEA SYMFONISK Sound Remote Gen 2)

`automations/sonos_remote.yaml` maps Z2M button events to media controls:

| Button | Action |
|---|---|
| Play/pause | toggle, with cold-start picking a random Spotify playlist from `playlists` |
| Volume up / hold | +10 % per press |
| Volume down / hold | −10 % per press |
| Track next | `media_player.media_next_track` |
| Track previous | `media_player.media_previous_track` |
| Dot 1 (short release) | step backwards through the playlist pool |
| Dot 2 (short release) | step forwards through the playlist pool |

Cursor lives in `input_number.inkplate_sonos_playlist_index` (wraps via
modulo). The playlist pool is duplicated in three places (play/pause,
dot-1, dot-2) — keep them in sync.

## Deploy

```sh
make deploy-ha
# or with overrides
HA_HOST=${HA_HOST} HA_SSH_PORT=2222 HA_USER=root HA_SSH_KEY=~/.ssh/id_ed25519 make deploy-ha
```

The script:

1. Verifies SSH connectivity to the HAOS VM.
2. Optionally regenerates `sensors/news_sources.yaml` from
   `config/news_sources.yaml` (if you maintain RSS feed sensors for
   custom dashboards).
3. Wipes `/config/custom/inkplate/*` (preserving `state/` runtime artifacts).
4. Streams the `ha/` tree over SSH and untars on the VM.
5. Streams `secrets.yaml` separately to `/config/custom/inkplate/secrets.yaml`.
6. Runs `ha core check && ha core restart` (full restart — `ha core reload`
   doesn't pick up newly-introduced helpers / entities).
7. Tails the recent HA log for visible errors.

A 30-60 s blackout window during the restart is normal.

## Rollback

```sh
ssh root@<HA_HOST> -p <HA_SSH_PORT>
rm -rf /config/custom/inkplate
# remove the three include lines from /config/configuration.yaml
ha core check && ha core restart
```

Native HA integrations (weather, sun, moon, Sonos, MQTT) can stay —
they're idempotent.

## One-time setup

See [`../SETUP.md`](../SETUP.md) for the full operator install across
all four hosts. The HA-specific bits in summary:

1. Install **Mosquitto broker** (MQTT) and **Advanced SSH & Web
   Terminal** (deploy path) add-ons.
2. Add the three include lines to `configuration.yaml`.
3. Copy `secrets.yaml.example` → `secrets.yaml` and fill in (HA
   long-lived token, renderer auth header, MQTT creds, Anthropic API
   key only if regenerating corpus seed).
4. `make deploy-ha`.
5. In HA UI: confirm `input_boolean.inkplate_publisher_enabled` is **on**
   (it's the master kill switch — silently turns every renderer
   publisher into a no-op when off).

## Common operator tasks

```sh
# Force the alternation tick to fire now (useful right after a deploy)
curl -H "Authorization: Bearer $HA_TOKEN" -X POST \
  -d '{"entity_id":"automation.inkplate_per_tier_face_alternation_tick"}' \
  http://$HA_HOST:8123/api/services/automation/trigger

# Skip Sonos to a different playlist (cycle via the dots, or pin via API)
curl -H "Authorization: Bearer $HA_TOKEN" -X POST \
  -d '{"entity_id":"input_number.inkplate_sonos_playlist_index","value":3}' \
  http://$HA_HOST:8123/api/services/input_number/set_value

# Reset the alternation phase to "tier-main" everywhere
curl -H "Authorization: Bearer $HA_TOKEN" -X POST \
  -d '{"entity_id":"input_number.inkplate_alternation_offset","value":0}' \
  http://$HA_HOST:8123/api/services/input_number/set_value
```

## Further docs

- [`docs/architecture.md`](docs/architecture.md) — component + data-flow diagram.
- [`docs/deploy.md`](docs/deploy.md) — deploy script details, env vars, rollback.
- [`docs/secrets-checklist.md`](docs/secrets-checklist.md) — every secret field, what it's for.
- [`docs/sleep-strategy.md`](docs/sleep-strategy.md) — quiet-hours + override interaction.
- [`docs/troubleshooting.md`](docs/troubleshooting.md) — known failure modes.
