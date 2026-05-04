# ha-integrations Specification — delta

## ADDED Requirements

### Requirement: Night-poetic-line generation is pool-driven and English-only

HA SHALL generate the Night face's poetic weather line by random selection from a curated, operator-edited pool of pre-written English lines, keyed by weather bucket. There SHALL be no live LLM invocation in the path.

The pool SHALL live at `ha/config/night_poetic_pool.yaml`. The picker `shell_command.generate_poetic_weather_line` SHALL pick one line at random from `pool[bucket]`, validate it, and write it to `/config/custom/inkplate/state/poetic_weather.txt`.

#### Scenario: No Anthropic API key, no LLM, no degradation

- **WHEN** `ha/secrets.yaml` has `anthropic_api_key` unset, expired, or rate-limited
- **THEN** the poetic-line pipeline is unaffected — the picker reads the pool and emits a valid line. The `generate_astro_event.py` pipeline (which still uses the key) is independent and may degrade separately.

### Requirement: Line stays stable across an unchanging bucket

HA SHALL re-pick the poetic line **only when the bucket changes**, not on a fixed cadence. As long as the computed bucket value is unchanged, the line written to `state/poetic_weather.txt` SHALL NOT be rewritten.

To implement this, HA SHALL expose `sensor.inkplate_night_poetic_bucket` as a template sensor whose state is the bucket key derived from the current weather entity's condition + temperature. The line-generation automation SHALL use a `state` trigger on this sensor (with `not_to: [unknown, unavailable]`) plus a `homeassistant.start` safety trigger, and SHALL NOT use a recurring time-pattern trigger.

The picker is invoked exactly once per bucket transition (plus once on each HA start). Between transitions the panel keeps the same line.

#### Scenario: Same bucket all night, same line all night

- **WHEN** the weather stays at `clear-night` and 3°C from 22:00 through 06:00, so the bucket is `clear_cold` for the whole window
- **THEN** the picker fires exactly once at the bucket-entry transition; the line written at that moment stays on the panel for the full 8-hour window. No hourly rewrites occur.

#### Scenario: Bucket transitions mid-night

- **WHEN** the weather shifts from `clear-night` to `partlycloudy` at 02:14 — the bucket value transitions from `clear_cold` to `partly_cloudy`
- **THEN** the bucket sensor's `state_changed` event fires, the automation fires, the picker reads the pool's `partly_cloudy` bucket, writes a new line. The line on the panel changes once at 02:14 and stays until the next bucket transition.

#### Scenario: Weather provider goes unavailable

- **WHEN** the source weather entity goes to `unavailable` (provider outage), causing the bucket sensor to also go `unavailable`
- **THEN** the automation does NOT fire (the trigger has `not_to: [unknown, unavailable]`); the line on the panel stays at whatever was last written. When the provider returns and the bucket re-evaluates, the automation fires once and writes a fresh line.

#### Scenario: HA restart re-publishes the current bucket's line

- **WHEN** Home Assistant restarts at 23:50 with weather still at `clear-night` 3°C
- **THEN** the `homeassistant.start` trigger fires the automation, the picker writes a line for `clear_cold`. Note: this MAY change the line on the panel even though the bucket itself hasn't changed — but only across an HA restart, which is rare.

### Requirement: Poetic-line schema and pool quality rules

Each line in the pool SHALL conform to:

- **Charset**: `[A-Za-z0-9 ,.:;!\-'"]+` — ASCII letters, digits, space, and the punctuation set listed. No Romanian diacritics, no emoji, no curly quotes, no em-dashes, no other punctuation.
- **Length**: 1 ≤ graphemes ≤ 40 (matches the renderer's `poetic_line` zone budget).
- **Voice**: plain, observational, slightly melancholy. Not clever-clever, not declarative, not advice.

The picker SHALL filter out any pool entry that violates charset or length rules. If all entries in the bucket fail the filter, the picker SHALL try the `cloudy` bucket as fall-through; if that also fails, it SHALL emit the literal string `"Quiet night."`.

#### Scenario: Malformed pool entry is filtered

- **WHEN** an operator deploys a pool with a `clear_cold` entry containing a Romanian diacritic (e.g., "Stele și frig")
- **THEN** the picker filters that entry out, picks from the remaining valid `clear_cold` entries, and writes a valid English line. The malformed entry is silently skipped (no automation failure).

#### Scenario: Bucket key missing from pool

- **WHEN** the bucket template in the automation produces a key that doesn't exist in the pool YAML (e.g., a new condition value that was never added)
- **THEN** the picker falls through to `cloudy`, picks from there, and writes a line. No HA log spam beyond a single "bucket missing, falling back" warning.

### Requirement: Pool growth guidance for operators

Each bucket in `night_poetic_pool.yaml` SHALL contain at least one entry — the picker depends on this for the per-bucket fallthrough. Operators SHOULD aim for 8-15 entries per bucket to keep visible repetition below the threshold a normal observer notices.

This is operator hygiene, not a hard rule enforced by automation. The picker functions correctly with a 1-entry bucket (it'd just always pick that one entry), but visible repetition becomes obtrusive.

#### Scenario: Pool with thin bucket renders the same line repeatedly

- **WHEN** the `sleet` bucket has only 2 entries and the weather sleets for 6 hours
- **THEN** the rendered Night face will show one of those 2 lines roughly evenly across the 6 hours; entries will repeat several times. This is acceptable behavior; the remedy is to add more entries to the pool, not to change the picker.

### Requirement: Removed `poetic_weather_line.yaml` config file

`ha/config/poetic_weather_line.yaml` (which previously held provider/model configuration for the LLM call) SHALL be removed from the deployed HA tree. The picker no longer reads provider/model configuration; the pool YAML file is the only configuration surface.

#### Scenario: Deploy with no `poetic_weather_line.yaml`

- **WHEN** the operator runs `ha/deploy.sh` after deleting `ha/config/poetic_weather_line.yaml`
- **THEN** the deploy succeeds; HA reload completes without error; `shell_command.generate_poetic_weather_line` runs normally on its hourly schedule
