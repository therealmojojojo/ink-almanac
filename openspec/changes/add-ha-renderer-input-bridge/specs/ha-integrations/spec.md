## ADDED Requirements

### Requirement: Renderer-input publishers

HA SHALL publish the renderer's JSON inputs via `POST http://{renderer_host}:{renderer_port}/inputs/<name>` with `Authorization: Bearer <renderer_input_token>`. One automation per input, each driven by a trigger appropriate to the input's freshness requirement:

| Input | Trigger(s) | Body source |
|---|---|---|
| `clock` | `time_pattern` every 1 minute | current local wall-clock formatted `{time: "HH:MM", date: "Weekday · Month D"}` |
| `weather` | state change on any renderer-facing weather template sensor; safety republish every hour; `homeassistant.start` | `{locations: [...], astro: {...}, poetic: <line>}` composed from weather template sensors, astro sensors, and `ha/state/poetic_weather.txt` |
| `climate` | state change on kitchen climate sensors; `homeassistant.start`; gated by a template condition checking sensor availability | `{inside: {temp, humidity?}}` (battery removed) |
| `hn` | state change on `sensor.inkplate_hn_top5`; `homeassistant.start` | `{items: [{title, subtitle}, ...]}` |
| `device` | MQTT trigger on `inkplate/state/device`; `homeassistant.start` | `{battery: {percentage, voltage}, build, last_seen}` sourced from the retained MQTT payload |

The `sonos` and `pairing` inputs have existing writers (`fetch_sonos_art.sh` via SSH on track-change; `generate_pairings_week.sh` on Sunday 23:30) and are not part of this requirement's scope; they are documented in `ha/docs/architecture.md` for completeness.

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
