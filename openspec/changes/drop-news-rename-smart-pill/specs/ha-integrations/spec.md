# ha-integrations — delta

## MODIFIED Requirements

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

## REMOVED Requirements

### Requirement: Hacker News and news sources

**Reason**: The device does not surface news of any kind. The Hacker News REST sensor, the per-source RSS sensors generated from `ha/config/news_sources.yaml`, and the supporting generator script `ha/scripts/generate_news_sensors.py` were dormant after the curated-news regen pipeline was removed (see archived change `drop-curated-news-regen` per commit `89c24e2`). The operator confirmed they will not be re-enabled. Keeping them in the spec misled future readers into thinking news content was a live face requirement.

**Migration**: the following HA assets are deleted from the repo:

- `ha/config/news_sources.yaml`
- `ha/sensors/news_sources.yaml` (auto-generated)
- `ha/scripts/generate_news_sensors.py`

The `ha/deploy.sh` "Regenerate per-source news sensors" block is removed. The `ha/docs/architecture.md` directory tree, inputs table, and the `ha/docs/troubleshooting.md` `sensor.news_digi24` entry are updated. The Summary face's bottom-band content is now sourced exclusively from the smart-pill body (see `rendering-pipeline`'s renamed input and `dashboard-faces`' Summary face requirement).
