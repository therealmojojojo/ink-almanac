## ADDED Requirements

### Requirement: Cache file contract

The poetic weather line SHALL live at a stable, renderer-readable path — e.g., `ha/state/poetic_weather.txt` on the Mac host, or an HA `template` sensor the renderer queries via REST. The file format is a single UTF-8 line, no trailing newline required.

#### Scenario: Renderer reads the line

- **WHEN** Night mode is rendered and the poetic weather cache file exists
- **THEN** the rendered face displays the cached line in italic Fraunces at the specified size

### Requirement: Generation cadence

The line SHALL be regenerated no more than once per hour during hours when Night mode is potentially active (21:00–07:00 by default). Outside that window, the cache MAY hold a stale value but SHALL be refreshed on the next boundary crossing into Night hours.

#### Scenario: Hourly refresh

- **WHEN** it is 22:00 and the cache was last written at 21:00
- **THEN** a new line is generated and written to the cache by 22:05

#### Scenario: Idle during day

- **WHEN** it is 14:00
- **THEN** no poetic-weather-line generation runs

### Requirement: Length and safety constraints

Generated lines SHALL be:

- ≤32 characters (the Night-face zone budget)
- ASCII + Romanian diacritics only (`ă â î ș ț` acceptable)
- Free of emoji, markdown, quotes, trailing punctuation ambiguity
- Evocative of the current weather without being literal (e.g., "Rain on the windows." beats "Rain at 16mm/h.")

Generated lines failing these constraints SHALL be rejected; the automation SHALL fall back to a hand-curated pool of lines tagged by weather condition.

#### Scenario: LLM output too long

- **WHEN** the LLM returns a line of 48 characters
- **THEN** the line is rejected, a fallback is selected from the hand-curated pool, and the rejection is logged

#### Scenario: LLM output contains emoji

- **WHEN** the LLM returns "Rain falls quietly. ☔"
- **THEN** the line is rejected and a fallback is used

### Requirement: Hand-curated fallback pool

A fallback pool at `ha/config/night_fallback_lines.yaml` SHALL contain ~50 vetted lines keyed by weather condition and temperature bucket:

```yaml
clear_cold:        ["Clear, quiet night.", "Cold, still sky.", "Stars over frost."]
clear_mild:        ["Clear, mild night.", ...]
rain:              ["Rain on the windows.", ...]
snow:              ["Snow by morning.", ...]
wind:              ["Wind along the eaves.", ...]
cloudy:            ["Heavy sky, quiet street.", ...]
overcast_warm:     [...]
# etc
```

The fallback pool SHALL be operator-editable.

#### Scenario: Fallback on rainy night

- **WHEN** the LLM is unavailable and the current weather is rainy
- **THEN** a line is chosen randomly from the `rain` bucket of the fallback pool

### Requirement: Provider choice

The LLM provider SHALL be configurable — `claude` (cloud, default) or `ollama` (local). Provider selection is via `ha/config/poetic_weather_line.yaml` with fields for provider, model, and any provider-specific parameters.

Claude provider SHALL use a small model (Haiku-class by default) with prompt caching for the system instructions, to minimize cost.

#### Scenario: Switching provider

- **WHEN** the operator edits the config to select `ollama` with model `llama3.2` and redeploys
- **THEN** subsequent hourly runs call the local Ollama endpoint; no cloud API is invoked

### Requirement: Minimal prompt

The prompt SHALL be deliberately small — a system instruction (cached) plus a single user message containing the current weather summary (condition + temperature + wind). The output SHALL be a single line.

#### Scenario: Prompt structure

- **WHEN** a generation runs with system prompt cached and user message "Current: overcast, 4°C, light wind"
- **THEN** the API call is small (system-cached, user text ~30 tokens) and the response is a single evocative line
