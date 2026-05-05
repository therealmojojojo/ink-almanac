# ha-integrations Specification

## Purpose
TBD - created by archiving change add-ha-renderer-input-bridge. Update Purpose after archive.
## Requirements
### Requirement: Renderer-input publishers

HA SHALL publish the renderer's JSON inputs via `POST http://{renderer_host}:{renderer_port}/inputs/<name>` with `Authorization: Bearer <renderer_input_token>`. One automation per input, each driven by a trigger appropriate to the input's freshness requirement:

| Input | Trigger(s) | Body source |
|---|---|---|
| `clock` | `time_pattern` every 1 minute | current local wall-clock formatted `{time: "HH:MM", date: "Weekday · Month D"}` |
| `weather` | state change on any renderer-facing weather template sensor; safety republish every hour; `homeassistant.start` | `{locations: [...], astro: {...}, poetic: <line>}` composed from weather template sensors, astro sensors, and `ha/state/poetic_weather.txt` |
| `climate` | state change on kitchen climate sensors; `homeassistant.start`; gated by a template condition checking sensor availability | `{inside: {temp, humidity?}}` (battery removed) |
| `hn` | state change on `sensor.inkplate_hn_top5`; `homeassistant.start` | `{items: [{title, subtitle}, ...]}` |
| `device` | MQTT trigger on `inkplate/state/device`; `homeassistant.start` | `{battery: {percentage, voltage}, build, last_seen}` sourced from the retained MQTT payload |

The `sonos` and `pairing` inputs have existing writers (`fetch_sonos_art.sh` via SSH on track-change; `generate_triplets.sh` operator-fired one-shot for the full triplet pool) and are not part of this requirement's scope; they are documented in `ha/docs/architecture.md` for completeness.

All five publisher automations SHALL be gated by `input_boolean.inkplate_publisher_enabled` (default `on`) as a master kill-switch for rollback.

HA SHALL configure the `rest_command`s with no retry — a failed POST is logged but the next natural trigger re-publishes. The renderer's 204 response is not checked; any non-2xx response is logged at `warning`.

#### Scenario: First boot populates every input

- **WHEN** HA starts fresh after a reboot and the renderer is reachable
- **THEN** within 30 s all five publishers have issued at least one POST, and `renderer/inputs/*.json` mtimes on the Mac host are all within the last 30 s

#### Scenario: Clock minute-tick

- **WHEN** the wall-clock minute rolls over
- **THEN** HA POSTs a clock body with the new `HH:MM` to `/inputs/clock` within 2 s

#### Scenario: Weather change republishes

- **WHEN** MET.no updates ${PLACE_A_NAME}'s current temperature and the weather template sensor transitions
- **THEN** HA POSTs a full weather body (both locations + astro + poetic) to `/inputs/weather`; no intermediate single-field updates are pushed

#### Scenario: Device state republishes on every wake

- **WHEN** the device publishes to retained MQTT `inkplate/state/device` on wake
- **THEN** HA's MQTT trigger fires and POSTs the new body to `/inputs/device`, with `last_seen` set to the HA-side receive time

#### Scenario: Publisher disabled

- **WHEN** the operator toggles `input_boolean.inkplate_publisher_enabled` to `off`
- **THEN** subsequent triggers do NOT POST to the renderer; the renderer continues serving from whatever files are on disk

#### Scenario: Renderer unreachable

- **WHEN** the renderer is down and HA's publisher fires
- **THEN** HA logs the connection failure at `warning` level and the automation completes without raising; no retry is scheduled

### Requirement: Renderer input token

A shared secret `renderer_input_token` SHALL be stored in `ha/secrets.yaml` and in the renderer's runtime environment (`RENDERER_INPUT_TOKEN`). The token is used as the bearer value for every `POST /inputs/:name` request. The example file `ha/secrets.yaml.example` SHALL document the field with a generation hint (e.g., `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`).

#### Scenario: Token missing

- **WHEN** `renderer_input_token` is absent at HA start
- **THEN** the publisher automations log a startup warning and do not fire; Summary/Weather/etc. continue to render from whatever inputs are on disk

### Requirement: Deploy-from-repo workflow

Home Assistant configuration for this project SHALL live in the `ha/` directory in this repo, not in the HAOS VM's `/config/` directly. The `ha/deploy.sh` script SHALL rsync `ha/` into `/config/custom/inkplate/` on the HAOS VM over SSH, then trigger an HA configuration reload.

Operator edits to HA happen here, in the repo. In-VM edits are considered drift and SHALL be reconciled by copying the in-VM state back into `ha/` (if intentional) or discarded (if accidental).

#### Scenario: Deploy changes

- **WHEN** the operator edits `ha/automations/schedule.yaml` and runs `make deploy-ha` (or `ha/deploy.sh`)
- **THEN** the changes are rsync'd to `/config/custom/inkplate/automations/schedule.yaml` in the HAOS VM, and HA reloads automations

#### Scenario: Deploy with SSH credentials missing

- **WHEN** the SSH key for the HA SSH add-on is not configured
- **THEN** `ha/deploy.sh` exits non-zero with a clear message about the missing key and the path to configure it

### Requirement: Weather integration for two locations

HA SHALL expose weather for ${PLACE_A_NAME} (home) and ${PLACE_B_NAME} (mountains, 900m) as two independent weather entities or equivalent. Each exposes at minimum:

- Current temperature (°C)
- Current conditions text
- Feels-like temperature
- High/low for today (°C)
- Rain probability (%)
- 5-day forecast: day, condition, high, low

The primary provider SHALL be one of MET.no or OpenWeatherMap (configurable). A secondary provider SHALL be configured as a fallback for when the primary is degraded; the fallback logic is HA's native weather-composition or a custom template sensor.

#### Scenario: Both locations reachable

- **WHEN** the renderer fetches the weather zone inputs for Weather mode
- **THEN** both ${PLACE_A_NAME} and ${PLACE_B_NAME} weather entities provide all required fields

#### Scenario: Primary weather provider fails

- **WHEN** MET.no returns an error for one location
- **THEN** HA's fallback logic substitutes OpenWeatherMap data for that location within 5 minutes, and the renderer continues receiving complete inputs

### Requirement: Indoor climate

An indoor climate source SHALL provide temperature and humidity values for the kitchen. Implementation is operator-choice (existing ESP sensor, ESPHome device, integration of a purchased unit). Whatever is chosen SHALL expose two entities: `sensor.kitchen_temperature`, `sensor.kitchen_humidity`.

#### Scenario: Summary render with climate

- **WHEN** Summary is rendered
- **THEN** the climate zone displays the current kitchen temperature and humidity from the configured entities

### Requirement: Sonos integration

HA's native Sonos integration SHALL be configured for the kitchen speaker. The following attributes SHALL be reachable via `media_player.kitchen_sonos`:

- `state` (`playing`, `paused`, `idle`, `unavailable`)
- `media_content_id`
- `media_title`, `media_artist`, `media_album_name`
- `entity_picture`

The following attribute MAY be absent (e.g. Spotify/streaming playback) and consumers MUST treat it as optional:

- `source` — when missing, a display label MAY be derived from `media_content_id` prefix (e.g. `x-sonos-spotify:` → "Spotify").

The entity name SHALL match the `kitchen_sonos_entity` helper value used by `now-playing-override`.

#### Scenario: Sonos entity reachable

- **WHEN** the operator queries `media_player.kitchen_sonos` via the HA REST API
- **THEN** all required attributes are present when playback is active

### Requirement: Hacker News and news sources

A REST sensor SHALL fetch the top N Hacker News stories every 30 minutes. The sensor SHALL expose at minimum, for each story: title, domain/subtitle, URL, score. Initial N is 5; Summary displays up to 2.

Additional news sources SHALL be configurable via `ha/config/news_sources.yaml`, each with a source name, fetch URL, and a response-shape hint (JSON path or XML/RSS). At minimum, one Romanian news source SHALL be configured at initial deploy so Summary's news carries Romanian-language content.

#### Scenario: HN sensor updates

- **WHEN** HN has new top stories and 30 minutes have elapsed since the last refresh
- **THEN** the HA HN sensor's state and attributes reflect the new stories

#### Scenario: Adding a Romanian news source

- **WHEN** the operator adds an entry to `news_sources.yaml` with `name: digi24`, `url: <rss-feed>`, and redeploys
- **THEN** a new HA sensor is available representing that source, and Summary's renderer can reference it via its input contract

### Requirement: Astro data

HA SHALL expose:

- Sunrise and sunset times for the operator's local location (via `sun.sun` or equivalent)
- Daylight duration (derived)
- Current moon phase (via the built-in `moon` sensor)
- Next full moon date (derived by a template sensor walking the `moon` integration)
- A grounded short statement for the Stars cell, refreshed daily, that
  summarises tonight's most interesting astronomical or space-science
  fact for a stargazer reader. This statement SHALL be sourced from:
  - **Skyfield** + the DE421 ephemeris file installed on the operator
    VM, computing tonight's planet visibility windows, peak altitudes
    and cardinal directions, close approaches, and active meteor
    showers for the panel's lat/lon
  - **Launch Library 2** (`ll.thespacedevs.com`) — upcoming launches
  - **Spaceflight Now** and **NASASpaceflight** RSS feeds — narrative
    space-news headlines from the last ~7 days

  The fact-block is passed verbatim to Claude Haiku, which acts only
  as a phrasing layer. The resulting statement is written to
  `/config/custom/inkplate/state/astro_event.txt`. The model SHALL be
  instructed to skip routine launches (Starlink, generic comm-sat) as
  noise, prioritise crewed/lunar/Mars/novel-vehicle/science-payload
  events and rare planetary events, and never mention the moon (the
  Moon cell handles that).

The daily refresh SHALL run at 07:00 local time so the cell is correct
from breakfast onward for the *upcoming* night.

The publisher SHALL implement a freshness guard: when
`astro_event.txt` mtime is older than 30 hours, the command-line
sensor returns the empty string, and the renderer falls back to the
"no event tonight" treatment. Stale text SHALL NOT be surfaced.

#### Scenario: Weather face astro footer renders

- **WHEN** Weather is rendered
- **THEN** the astro footer receives sunrise, sunset, moon-phase SVG
  hint, next-full-moon date, and tonight's Stars statement (if any)
  from HA

#### Scenario: Stars cell after a successful morning run

- **WHEN** `generate_astro_event.py` runs at 07:00 with live Skyfield,
  LL2, and RSS responses
- **THEN** `astro_event.txt` contains a single short statement that
  refers only to objects/events present in the input fact-block; the
  statement does not mention the moon

#### Scenario: Stars cell when LLM output is unparseable

- **WHEN** Haiku returns text that cannot be parsed as the expected
  JSON shape
- **THEN** the helper writes a deterministic Skyfield-derived phrase
  (highest-altitude visible planet with its compass direction and
  visibility window) instead of the raw model output

#### Scenario: Stars cell when the cron does not run

- **WHEN** `astro_event.txt` mtime is 36 hours old (yesterday's run
  succeeded but today's failed silently)
- **THEN** `sensor.astro_event_tonight` reports an empty string and
  the renderer surfaces the literal "no event tonight" text rather
  than yesterday's stale statement

### Requirement: Scheduled-mode automation

An HA automation SHALL implement the mode-schedule transitions:

- 06:30 → Summary becomes the scheduled face
- 10:00 → Gallery becomes the scheduled face
- 22:00 → Night becomes the scheduled face

On each transition, HA SHALL update the active-override helper to reflect the new scheduled face, and issue a wake signal to the device — unless a higher-precedence override is currently active (consult `now-playing-override`'s precedence rule).

#### Scenario: 10:00 transition without overrides

- **WHEN** it is 10:00, active override is `schedule`
- **THEN** the helper value updates, a wake signal is issued to the device, and the device fetches `/display/gallery.png` from the renderer

#### Scenario: 22:00 transition with active Now-Playing

- **WHEN** it is 22:00, music is playing, active override is `now_playing`
- **THEN** the schedule helper advances internally to Night, but no wake signal is issued until Now-Playing deactivates; when music stops and linger ends, the device wakes to fetch Night

### Requirement: Operator-fired triplet generation trigger

HA SHALL register `shell_command.generate_triplets` running `ha/scripts/generate_triplets.sh`, which SSH-invokes `python3 pairing/corpus_build_triplets_v2.py --apply` on the renderer host. The shell command SHALL be operator-fired (HA Developer Tools → Services), not on a time cadence.

The generator runs to exhaustion: every invocation regenerates the *entire* triplet pool under `corpus/_triplets/*.yaml`, capped by `PER_ITEM_CAP` and the recency window. One run produces ≈870 triplets at the current corpus size — roughly 2.5 years of one-per-day rotation. Re-runs are warranted only when the corpus grows materially or generation parameters change.

#### Scenario: Operator fires generate_triplets

- **WHEN** the operator calls `shell_command.generate_triplets` from HA Developer Tools → Services
- **THEN** the SSH-wrapped python invocation runs to completion, `corpus/_triplets/` is fully rewritten, and the shell command's return code, stdout, and stderr are visible in the HA service-call response

#### Scenario: Generation fails on the host

- **WHEN** the SSH command exits non-zero (host unreachable, python error, corpus invalid)
- **THEN** the HA service call surfaces the non-zero return code and stderr; HA does not auto-retry; the existing `corpus/_triplets/` content remains untouched until a successful run completes

### Requirement: Poetic weather line automation

An HA automation SHALL run every hour producing a short (≤32 chars) italic weather line for Night mode. Input is the current weather (primary location); output is a string cached to a file path the renderer reads.

The LLM used is configurable — local Ollama or Claude API. Default provider is Claude API (small, cheap model) unless the operator chooses local. The generated line SHALL be validated to ≤32 chars and to be family-safe; failing lines SHALL trigger a fallback string from a hand-curated pool.

#### Scenario: Clear-night line

- **WHEN** the weather for the primary location is clear and cold, and the hourly trigger fires
- **THEN** a line similar to "Clear, quiet night." is written to the cache file, and Night mode's next render uses it

#### Scenario: LLM unavailable

- **WHEN** the LLM call fails
- **THEN** a hand-curated fallback line matching the weather tone is written instead, and the renderer proceeds without distinguishing

### Requirement: Low-battery notification

The device reports battery percentage as part of its state. When the reported battery falls below 20%, HA SHALL send a notification to the operator's phone. Re-notification SHALL throttle — no more than one notification per 4 hours for the same threshold crossing.

#### Scenario: Battery dips below 20%

- **WHEN** the device reports 18% battery
- **THEN** an HA notification is sent to the operator's phone within 2 minutes, and no additional notifications for this crossing are sent for 4 hours

### Requirement: Device sleep-strategy helpers

HA SHALL expose the following input helpers consumed by the device's sleep strategy (per `device-firmware`). Each is published to a retained MQTT topic the device reads on wake.

- `input_datetime.sonos_active_start` (time) — default `07:00:00`
- `input_datetime.sonos_active_end` (time) — default `20:00:00`
- `input_datetime.quiet_start` (time) — default `00:00:00`
- `input_datetime.quiet_end` (time) — default `05:00:00`
- `input_number.fast_path_interval_seconds` — default `180`, min `60`, max `600`

When any of these helpers change, HA SHALL re-publish the retained MQTT values so the device picks up the new settings on its next natural wake.

#### Scenario: Adjusting Sonos active hours

- **WHEN** the operator updates `input_datetime.sonos_active_end` from `20:00` to `22:00`
- **THEN** HA publishes the new value to the retained sleep-strategy topic, and the device's next wake applies the new window

### Requirement: Active-override helper

HA SHALL maintain helper entities tracking the currently-active override (consumed by `now-playing-override` and the scheduled-mode automation). At minimum:

- `input_text.active_override` — one of `schedule`, `now_playing`, `weather_peek`, `summary_gallery_toggle`
- `input_text.prior_override` — saved state for restoration after Now-Playing
- Other helpers as defined by `now-playing-override`

#### Scenario: Override state visible

- **WHEN** the operator queries `input_text.active_override`
- **THEN** the current active override is reflected

### Requirement: Secrets

API keys and other credentials SHALL live in `ha/secrets.yaml` (deployed to `/config/secrets.yaml` on the VM). The repo SHALL include `ha/secrets.yaml.example` with placeholders; the real `secrets.yaml` is gitignored.

#### Scenario: Committing secrets

- **WHEN** the operator accidentally stages `ha/secrets.yaml`
- **THEN** the root `.gitignore` rule for `ha/secrets.yaml` prevents the commit

### Requirement: Operator-editable wake schedule

HA SHALL host an operator-editable wake-schedule definition at `ha/config/wake_schedule.yaml`. The file SHALL contain exactly four named tiers (`night`, `morning`, `midday`, `evening`) with `start` (HH:MM), `full_min`, `poll_min`, `partial_min` per tier, plus a `version` field at the top level. There is no `partial_brings_poll` field — partials are always offline; operators who want MQTT-based mode-change pickup between Fulls declare a positive `poll_min`.

`ha/deploy.sh` SHALL deploy this file to the HAOS VM at `/config/custom/inkplate/config/wake_schedule.yaml`. The file lives next to the other operator-editable configs (`night_fallback_lines.yaml`, `poetic_weather_line.yaml`, etc.) and follows the same edit-and-redeploy workflow.

#### Scenario: Operator changes Midday cadence

- **WHEN** the operator edits `ha/config/wake_schedule.yaml` to change `midday.full_min` from 30 to 60 and runs `ha/deploy.sh`
- **THEN** the rendered YAML is rsync'd to `/config/custom/inkplate/config/`, HA reloads, the publish-wake-schedule automation fires on `homeassistant.start` (or its file-watch trigger), and the new JSON-form schedule is published retained to `inkplate/command/schedule`

### Requirement: Wake-schedule publisher automation

HA SHALL register an automation `inkplate_publish_wake_schedule` that:

- Triggers on `homeassistant.start`.
- Triggers on changes to `wake_schedule.yaml` (file-mtime change, or via a deploy-set `input_boolean.inkplate_wake_schedule_dirty` flag toggled by the deploy script after rsync).
- Reads the YAML file, validates it minimally (version present, four tiers present, `start` parseable), and renders to the canonical JSON shape per the device-wake-protocol spec.
- Publishes the JSON retained to `inkplate/command/schedule`.
- Logs the publish at `info` level so operators see it landed.

The automation SHALL be gated by `input_boolean.inkplate_publisher_enabled` (the master kill-switch, same as other publishers).

#### Scenario: HA-start publishes the current schedule

- **WHEN** HA boots fresh
- **THEN** within 10 s of `homeassistant.start`, the automation fires, reads the YAML, publishes the JSON retained to `inkplate/command/schedule`, ensuring the broker holds the operator's current schedule for any device wake that follows

#### Scenario: Master kill-switch

- **WHEN** the operator toggles `input_boolean.inkplate_publisher_enabled` to off and edits `wake_schedule.yaml`
- **THEN** the automation does not publish; the broker continues to hold whatever the previous publish was; the device runs on its cached schedule indefinitely

### Requirement: Minimal HA-side validation before publish

The publisher automation SHALL refuse to publish a YAML that fails any of these structural checks: missing `version`, missing tiers, tier count != 4, unknown tier name, unparseable `start`. On refusal it SHALL log a warning and leave the previously-published retained payload intact — so a typo'd YAML doesn't take the device off-cadence.

The full bounds + divisibility check is done device-side (per the device-firmware spec). HA validates only the structural shape; the device is the authority on numerical validity. This split keeps Jinja-template logic small and avoids duplicating the bounds rules in two places.

#### Scenario: Operator deploys YAML with missing tier

- **WHEN** the operator deploys `wake_schedule.yaml` with only three tiers (`night`, `morning`, `midday`) and no `evening`
- **THEN** the automation logs the refusal at `warning` level and does NOT publish; the retained `inkplate/command/schedule` topic remains unchanged; the device continues on its previously-cached schedule

### Requirement: Schedule-acknowledgement visibility

HA SHALL expose the device's currently-active schedule hash as `sensor.inkplate_device_schedule_hash`, sourced from the `schedule_hash` field of the retained `inkplate/state/device` JSON payload. The sensor's value MAY be displayed truncated, but the full 32-bit hex hash SHALL be available as the `hash_full` attribute.

The operator SHALL be able to compare this against the FNV-32 hash of the JSON HA most recently published. If they match, the device is running the operator's schedule. If they differ, the device hasn't yet picked up the new schedule (latest possible delay: one Full cycle, plus one wake to confirm via the next state/device publish).

The firmware therefore SHALL include the active `g_schedule_cache.payload_hash` in every state/device JSON publish under the key `schedule_hash`.

#### Scenario: Operator confirms the device picked up the new schedule

- **WHEN** the operator deploys a new `wake_schedule.yaml`, observes the publisher automation's log line confirming the publish, and then waits ≤ 30 min for a Full
- **THEN** the device's next state/device publish carries the new `schedule_hash`, HA's `sensor.inkplate_device_schedule_hash` updates to the new value, and the operator can verify it matches the hash of the just-published JSON

### Requirement: EPD power-good binary sensor and alert

HA SHALL expose `binary_sensor.inkplate_device_epd_power_good` reading the `epd_pwrgood` boolean from retained `inkplate/state/device`. The sensor SHALL use `device_class: problem` (so the `on` state means "wedged" / problem present, matching HA UX conventions).

HA SHALL register an automation that, when the binary sensor stays in the problem state for at least one full-cycle window (default `for: "00:31:00"` to cover the slowest Midday cadence), notifies the operator via `notify.inkplate_operator`. The notification SHALL state that the panel is wedged, that recovery requires removing the LiPo battery, and SHALL include the most recent battery percentage and wake_reason for context.

The automation SHALL apply a 4-hour re-notification throttle (matching `inkplate_low_battery_notify`) so a sustained outage does not produce a steady stream of identical alerts.

#### Scenario: Wedge detected and notified

- **WHEN** the device publishes `epd_pwrgood: false` on two consecutive full-cycle wakes (≥ 31 minutes apart in Midday)
- **THEN** HA emits a single `notify.inkplate_operator` notification stating the panel is wedged and prompting battery removal

#### Scenario: Transient PMIC fault not notified

- **WHEN** a single wake publishes `epd_pwrgood: false` but the next wake publishes `true`
- **THEN** the binary sensor flips on then off without exceeding the `for:` debounce window, and no notification is emitted

#### Scenario: Sustained wedge does not spam

- **WHEN** the panel stays wedged across a 12-hour window (the device keeps publishing `false` every 15-30 min)
- **THEN** the operator receives at most one notification every 4 hours



### Requirement: HA publishes the Now-Playing track-version topic

HA SHALL publish a retained MQTT message to `inkplate/state/now_playing_track` whenever the Sonos media player's `media_content_id` (or its title/artist/album fallback) changes while playing. The publish SHALL be integrated into the existing `inkplate_publish_sonos` automation (`ha/automations/publish_inputs.yaml`) as the FINAL action in its `action:` block, after the existing `rest_command.inkplate_publish_sonos` (which updates the renderer's `sonos.json`).

Payload: identical Jinja expression to the existing `input_text.inkplate_now_playing_content_id` helper:

```jinja
{{ state_attr('media_player.kitchen_sonos','media_content_id')
   or (state_attr('media_player.kitchen_sonos','media_title') ~ '|'
       ~ state_attr('media_player.kitchen_sonos','media_artist') ~ '|'
       ~ state_attr('media_player.kitchen_sonos','media_album_name')) }}
```

A YAML comment in the automation SHALL state the sequencing constraint ("MUST run after rest_command.inkplate_publish_sonos") so a future editor doesn't reorder the actions and reintroduce the renderer-vs-MQTT race.

#### Scenario: Sonos plays a new track → renderer + MQTT updated in order

- **WHEN** the operator presses play on a new track in Sonos
- **THEN** HA's `inkplate_publish_sonos` automation fires: first the `rest_command.inkplate_publish_sonos` POSTs the new track metadata to the renderer (`sonos.json` updated synchronously); then the `mqtt.publish` step writes the new track identifier to `inkplate/state/now_playing_track` retained. The device, on its next Poll wake, sees the new hash and fetches an image rendered against the up-to-date `sonos.json`

#### Scenario: HA start re-publishes both the renderer input and the track topic

- **WHEN** Home Assistant boots while Sonos is currently playing
- **THEN** the `inkplate_publish_sonos` automation fires on `homeassistant.start` (existing trigger), republishing both the renderer's `sonos.json` AND the retained MQTT track-version topic. The device's next NowPlaying Poll sees the (re-published) retained value and continues to dedupe correctly

#### Scenario: Volume / seek changes do NOT re-publish

- **WHEN** the operator adjusts Sonos volume or seeks within the current track (`media_content_id` unchanged)
- **THEN** `inkplate_publish_sonos`'s existing trigger does NOT fire (it triggers on state and media_content_id, not on every attribute), so neither the renderer publish nor the track-version MQTT publish runs. The device's NowPlaying Polls continue to find the same hash and stay quiet

### Requirement: HA mirrors `inkplate_active_override` to MQTT

HA SHALL run an automation (`ha/automations/publish_active_override.yaml` or appended to an existing automation file) that mirrors the value of `input_text.inkplate_active_override` to retained MQTT topic `inkplate/state/active_override`. The automation SHALL trigger on:

- State-change of `input_text.inkplate_active_override` (any value transition).
- `homeassistant.start` (re-publish after HA / broker restart).

Action: `mqtt.publish` with `topic: inkplate/state/active_override`, `payload: "{{ states('input_text.inkplate_active_override') }}"`, `retain: true`, `qos: 0`. Gated by `input_boolean.inkplate_publisher_enabled` per the existing publisher convention.

This mirror is what gives the device its session-aware cadence override — the device polls every minute while a Sonos session is active even when a peek has flipped active_mode away from now-playing.

#### Scenario: Sonos starts → override mirror flips → device picks up the cadence change

- **WHEN** Sonos transitions to playing (outside quiet hours), HA's `inkplate_sonos_play_start` flips `input_text.inkplate_active_override` to `now_playing`
- **THEN** the override-mirror automation fires (state-change trigger), publishes `inkplate/state/active_override = now_playing` retained; the device's next Full/Poll/PollPartial wake reads it, flips `session_now_playing` to true, and from this point pathForMinute returns Poll for every minute until the session ends

#### Scenario: Linger expiry → override mirror flips back

- **WHEN** Sonos has been paused, the linger timer expires, and HA's `inkplate_sonos_linger_expired` runs the restore cascade and sets `input_text.inkplate_active_override` to `schedule`
- **THEN** the override-mirror automation fires, publishes `inkplate/state/active_override = schedule` retained; the device's next wake reads it, flips `session_now_playing` to false, and from this point pathForMinute follows the tier dispatch (Fulls + Partials only under the operator's no-daytime-Polls config)
