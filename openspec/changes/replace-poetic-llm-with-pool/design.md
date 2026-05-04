# Design — Pool-only Night-poetic line

## Pipeline before vs. after

```
Before:                                          After:
  hourly time_pattern                              state_changed on
       │                                           sensor.inkplate_night_poetic_bucket
       ▼                                                │
  automation: compute bucket inline                     ▼
       │                                           automation: read bucket sensor
       ▼                                                │
  shell_command (LLM, fallback to pool)                 ▼
       │                                           shell_command (pool pick)
       ▼                                                │
  state/poetic_weather.txt                              ▼
       │                                           state/poetic_weather.txt
       ▼                                                │
  command_line sensor → renderer face                   ▼
                                                   command_line sensor → renderer face
```

Two structural changes:

1. **The bucket computation moves out of the automation** into a template sensor `sensor.inkplate_night_poetic_bucket`. The automation now reads the sensor's value rather than re-running the bucket template.
2. **The automation trigger flips from hourly to bucket-change.** A line is written exactly once per bucket transition. As long as the bucket stays the same, the line on the panel stays the same. Hourly churn is gone.

The output contract — a single line written to `state/poetic_weather.txt`, picked up by `sensor.inkplate_poetic_weather_line`, consumed by `renderer/src/modes/{night,weather}.ts` — is unchanged.

## File layout changes

| Path | Change |
|---|---|
| `ha/scripts/generate_poetic_weather_line.sh` | Slimmed from ~200 LOC to ~40 LOC; LLM block removed |
| `ha/config/night_fallback_lines.yaml` | Renamed → `ha/config/night_poetic_pool.yaml` (the file is no longer a fallback) |
| `ha/config/poetic_weather_line.yaml` | **Removed** — provider/model config is dead with the LLM gone |
| `ha/secrets.yaml` | `anthropic_api_key` stays (still used by `generate_astro_event.py`) |
| `ha/automations/poetic_weather.yaml` | Trigger swapped from hourly to bucket-state-change; bucket logic moves into a template sensor |
| `ha/sensors/poetic_weather_bucket.yaml` (new) | Template sensor `sensor.inkplate_night_poetic_bucket` carrying the bucket key |
| `ha/integrations/shell_commands.yaml` | Unchanged (still calls `generate_poetic_weather_line.sh`) |
| `ha/integrations/command_line_sensors.yaml` | Unchanged (still reads `state/poetic_weather.txt`) |

## Bucket template sensor

```yaml
# ha/sensors/poetic_weather_bucket.yaml
template:
  - sensor:
      - name: inkplate_night_poetic_bucket
        unique_id: inkplate_night_poetic_bucket
        availability: >-
          {{ states('weather.${PLACE_A_SLUG}_forecast') not in
             ['unknown','unavailable','none'] }}
        state: >-
          {%- set c = states('weather.${PLACE_A_SLUG}_forecast') -%}
          {%- set t = state_attr('weather.${PLACE_A_SLUG}_forecast','temperature') | int(0) -%}
          {%- if c in ['clear-night','sunny','clear'] -%}
            {%- if t <= 5 -%}clear_cold
            {%- elif t <= 18 -%}clear_mild
            {%- else -%}clear_warm{%- endif -%}
          {%- elif c == 'partlycloudy' -%}partly_cloudy
          {%- elif c in ['cloudy','overcast'] -%}
            {%- if t <= 5 -%}cloudy_cold{%- else -%}cloudy{%- endif -%}
          {%- elif c == 'fog' -%}fog
          {%- elif c == 'rainy' -%}rain
          {%- elif c == 'pouring' -%}pouring
          {%- elif c in ['lightning','lightning-rainy','hail','exceptional'] -%}thunderstorm
          {%- elif c == 'snowy' -%}snow
          {%- elif c == 'snowy-rainy' -%}sleet
          {%- elif c in ['windy','windy-variant'] -%}windy_dry
          {%- else -%}cloudy
          {%- endif -%}
```

The same template logic that's currently inline in `ha/automations/poetic_weather.yaml`, just lifted into a sensor so its value can be a state-change trigger.

## Automation rewrite

```yaml
# ha/automations/poetic_weather.yaml
- id: inkplate_poetic_weather_on_bucket_change
  alias: "Inkplate: Night-poetic line on bucket change"
  mode: single
  max_exceeded: silent
  trigger:
    - platform: state
      entity_id: sensor.inkplate_night_poetic_bucket
      not_to: ['unknown', 'unavailable']
    - platform: homeassistant
      event: start
  condition:
    - condition: state
      entity_id: input_boolean.inkplate_publisher_enabled
      state: "on"
    - condition: template
      value_template: >-
        {{ states('sensor.inkplate_night_poetic_bucket')
           not in ['unknown','unavailable','none',''] }}
  action:
    - service: shell_command.generate_poetic_weather_line
      data:
        bucket: "{{ states('sensor.inkplate_night_poetic_bucket') }}"
```

Net behavior: the line is written exactly once per bucket transition (plus once on HA start). If the weather stays in the same bucket for 8 hours, the panel shows the same line for 8 hours. The hourly time_pattern trigger is gone.

## Pool schema (in `night_poetic_pool.yaml`)

```yaml
# Top-level: bucket name → list of poetic line strings.
# Bucket names are produced by ha/automations/poetic_weather.yaml's bucket
# template; operator may add/remove/edit entries here without touching
# the automation.
#
# Per-line rules (validated by generate_poetic_weather_line.sh on every pick):
#   * ASCII letters, digits, spaces, and the punctuation set ,.:;!-'"
#     — no Romanian diacritics, no emoji, no curly quotes, no em-dashes
#   * Length 1..40 graphemes
#   * House voice: plain, observational, slightly melancholy; no clever-clever
#
# Operator guidance:
#   * 8-15 entries per bucket reduces visible repetition (a bucket of 8
#     repeats one entry per ~8 hours of identical weather; bigger pools
#     hide the rotation)
#   * Bucket fall-through: if a bucket key is missing, the picker tries
#     `cloudy`, then the literal "Quiet night." as a last resort

clear_cold:
  - "Clear, quiet night."
  - "Cold, still sky."
  - ...

clear_mild:
  - ...

# … one block per bucket
```

The validator regex is now strictly `[A-Za-z0-9 ,.:;!\-'"]+` (drops the prior allowance for `ĂÂÎȘȚăâîșț`).

## Picker script

```bash
#!/usr/bin/env bash
# ha/scripts/generate_poetic_weather_line.sh — pool-driven poetic line.
#
# Picks one line from ha/config/night_poetic_pool.yaml keyed by the bucket
# arg, validates it (ASCII + length), writes to state/poetic_weather.txt.
# No network, no LLM. ~40 lines.

set -euo pipefail

BUCKET="${4:-cloudy}"   # legacy positional args 1-3 (summary, temp, wind)
                         # are no longer used; kept so automation YAML
                         # doesn't need to change

BASE="/config/custom/inkplate"
POOL_FILE="$BASE/config/night_poetic_pool.yaml"
STATE_DIR="$BASE/state"
STATE_FILE="$STATE_DIR/poetic_weather.txt"
mkdir -p "$STATE_DIR"

LINE=$(POOL_FILE="$POOL_FILE" BUCKET="$BUCKET" python3 - <<'PY'
import os, random, re, sys, yaml
from pathlib import Path
data = yaml.safe_load(Path(os.environ["POOL_FILE"]).read_text()) or {}
b = os.environ.get("BUCKET", "cloudy")
lines = data.get(b) or data.get("cloudy") or ["Quiet night."]
allowed = re.compile(r"^[A-Za-z0-9 ,.:;!\-'\"]+$")
candidates = [l for l in lines if 1 <= len(l) <= 40 and allowed.match(l)]
if not candidates:
    print("Quiet night.")  # ultimate safety
    sys.exit(0)
print(random.choice(candidates))
PY
)

printf '%s\n' "$LINE" > "$STATE_FILE"
```

## Migration

1. Operator renames `ha/config/night_fallback_lines.yaml` → `ha/config/night_poetic_pool.yaml`.
2. Operator removes any Romanian-diacritic entries (today there are none in the file content; the schema *allowed* them but actual lines are English).
3. Operator deletes `ha/config/poetic_weather_line.yaml` (no longer read).
4. `ha/deploy.sh` propagates. Next hourly automation run uses the new pool-only path.

No firmware change. No HA restart needed (file changes pick up on next automation run).

## Test plan

- Smoke run: `bash generate_poetic_weather_line.sh "" "" "" "clear_cold"` returns a valid line on stdout, writes the same to state file.
- Schema check: a deliberately-broken pool entry (Romanian diacritics, > 40 chars, emoji) is filtered out by the picker; if all entries fail, the literal `"Quiet night."` is emitted.
- Bucket fallthrough: `bucket=nonexistent_bucket` falls to `cloudy` then to `"Quiet night."`.
- HA-side: invoking `service: shell_command.generate_poetic_weather_line` from Developer Tools updates the file mtime and the sensor's value.

## Why not just drop the LLM in-place without renaming?

Renaming `night_fallback_lines.yaml → night_poetic_pool.yaml` is a clarity-only change. The file is no longer a "fallback" — it's the source of truth. Keeping the old name would mislead future operators reading the config tree. It's a one-time rename in a deploy.

## What this enables (out-of-scope here, listed for context)

- **Schedule-push work** can rely on the poetic line being deterministic and instant. No more "did the LLM time out this hour?" failure mode bleeding into the schedule cadence.
- **Offline operation.** With this change, the entire Night face's content (except smart_pill from the daily pairing) is available without any external API call.
- **Backports of pool entries** between deployments are trivial — no model-version drift, no prompt-version drift.
