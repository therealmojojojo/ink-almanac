## ADDED Requirements

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
- Tonight's astronomical event (meteor shower, ISS pass, planetary conjunction, eclipse) — via a scraped or RSS feed from a reliable source (in-the-sky.org or similar)

#### Scenario: Weather face astro footer renders

- **WHEN** Weather is rendered
- **THEN** the astro footer receives sunrise, sunset, moon-phase SVG hint, next-full-moon date, and the night's event (if any) from HA

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
