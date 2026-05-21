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
| `device` | MQTT trigger on `inkplate/state/device`; `homeassistant.start` | `{battery: {percentage, voltage}, build, last_seen}` sourced from the retained MQTT payload |

The previous `hn` row is retired together with the Hacker News and news-sources requirement removed below.

The `smart_pill` and `pairing` inputs are written by `pairing/publish_today.py` (SSH-invoked daily) on the Mac host directly to `RENDERER_INPUTS_DIR`, not via this HTTP endpoint. They appear in the renderer's input contract (see `rendering-pipeline`) but not in this publishers table.

The `sonos` input has an existing writer (`fetch_sonos_art.sh` via SSH on track-change) and is not part of this requirement's scope; it is documented in `ha/docs/architecture.md` for completeness.

All publisher automations SHALL be gated by `input_boolean.inkplate_publisher_enabled` (default `on`) as a master kill-switch for rollback.

#### Scenario: Smart pill body lands without HA involvement

- **WHEN** `pairing/publish_today.py` runs at 06:00 and writes `renderer/inputs/smart_pill.json` directly via SSH
- **THEN** the renderer's next `/display/summary.png` request reads the new body; HA does not POST to `/inputs/smart_pill`

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

An HA automation SHALL produce a short observational weather line for Night mode by selecting from a hardcoded pool keyed by weather bucket. There is NO LLM call — the line is always picked deterministically from `ha/config/night_poetic_pool.yaml` (renamed from `night_fallback_lines.yaml`; the file is no longer a "fallback" since it's the only source of truth).

The pool SHALL contain at minimum 5 lines per bucket × 13 weather buckets = 65 lines, with 8 entries per bucket × 14 buckets = 112 lines as the current operator-curated content. Operators MAY extend any bucket toward 12-15 entries to reduce visible repetition during multi-night stretches of stable weather. Each line SHALL match the validator regex `^[A-Za-z0-9 ,.:;!\-'"]+$` (English ASCII subset, no diacritics, no emoji, no curly quotes, no em-dashes) and SHALL be ≤ 40 graphemes.

Bucket keys are: `clear_{cold,mild,warm}`, `partly_cloudy`, `cloudy{,_cold}`, `fog`, `drizzle`, `rain`, `pouring`, `thunderstorm`, `snow`, `sleet`, `windy_dry`.

The picker script `ha/scripts/generate_poetic_weather_line.sh` SHALL:

1. Read the bucket from its **last** positional arg (so legacy 4-arg invocations like `script.sh "{{ summary }}" "{{ temp_c }}" "{{ wind }}" "{{ bucket }}"` keep working during partial deploys — the first three positional args are ignored).
2. Open `night_poetic_pool.yaml`.
3. Shuffle `pool[bucket] or pool['cloudy'] or []`, walk the shuffled list, skip entries that fail the regex or length check, print the first that passes.
4. If all candidates fail (or both buckets are empty), print the hardcoded safety string `"Quiet night."`.
5. Write the chosen line to `state/poetic_weather.txt`.

The trigger model SHALL be **bucket-change**, not hourly. A new template sensor `sensor.inkplate_night_poetic_bucket` exposes the current bucket key (computed from the primary weather entity's condition + temperature + wind_speed; `wind_kph >= 25` overrides `cloudy` and `partly_cloudy` to `windy_dry`). The `inkplate_poetic_weather_bucket_change` automation fires on:

- `state_changed` of `sensor.inkplate_night_poetic_bucket` with `not_to: [unknown, unavailable, ""]`.
- `homeassistant.start` (safety re-publish).

Gated by `input_boolean.inkplate_publisher_enabled` (master kill-switch) and a time-of-day template condition that limits firing to night hours (21:00-07:00 local).

As long as the bucket stays the same (e.g., 8 hours of `clear_cold`), the same line stays on the panel. When weather shifts to a new bucket, one new line is picked from that bucket and stays until the next bucket change.

The provider config file `ha/config/poetic_weather_line.yaml` SHALL be removed (no provider selection, no LLM model name to configure). `ha/secrets.yaml`'s `anthropic_api_key` SHALL be retained — `generate_astro_event.py` still uses it.

#### Scenario: Bucket change picks a new line; stable weather doesn't churn

- **WHEN** the weather has been `clear_cold` for the past 4 hours, and stays `clear_cold`
- **THEN** the poetic line on the panel does NOT change. The automation does not fire because the bucket sensor's state does not transition

#### Scenario: Weather shifts from clear-cold to fog

- **WHEN** the primary weather entity transitions from `clear` to `fog` and the bucket sensor's state changes from `clear_cold` to `fog`
- **THEN** the automation fires once; the picker selects a random line from the `fog` bucket (e.g., "Fog at the street lamps."); writes it to `state/poetic_weather.txt`; the renderer's next Full pulls it via the `sensor.inkplate_poetic_weather_line` chain and bakes it into the Night PNG

#### Scenario: Bucket missing from pool falls through to cloudy

- **WHEN** the bucket sensor reports a value for which `night_poetic_pool.yaml` has no key (e.g., a future weather classification)
- **THEN** the picker falls back to `pool['cloudy']`. If that's also missing, falls back to the hardcoded safety string `"Quiet night."`

#### Scenario: HA restart re-publishes the line

- **WHEN** Home Assistant restarts
- **THEN** the automation fires on `homeassistant.start`, the picker writes a fresh line for the current bucket, and the line is available to the next Night Full

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

