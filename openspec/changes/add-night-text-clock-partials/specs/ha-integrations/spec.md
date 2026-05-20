# ha-integrations Specification — delta

## MODIFIED Requirements

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
