# Tasks — Pool-only Night-poetic line

## 1. Pool file

- [ ] 1.1 Rename `ha/config/night_fallback_lines.yaml` → `ha/config/night_poetic_pool.yaml`.
- [ ] 1.2 Replace the file content with the seed pool from `openspec/changes/replace-poetic-llm-with-pool/examples/night_poetic_pool.yaml` (5 lines per bucket × 13 buckets = 65 lines, plain observational voice, English-only).
- [ ] 1.3 Verify every line passes the validator regex `[A-Za-z0-9 ,.:;!\-'"]+` and is ≤ 40 graphemes.
- [ ] 1.4 (Operator follow-up, not blocking) Extend thin buckets toward 8-15 entries to reduce visible repetition across multi-night stretches of stable weather.

## 2. Picker script

- [ ] 2.1 Replace `ha/scripts/generate_poetic_weather_line.sh` with the slimmed pool-only picker (~40 LOC). Drop all LLM-related code: API key loading, request body, response parsing, length-clamping, fallback-decision tree.
- [ ] 2.2 Validate behavior with a deliberately-broken pool entry (regex fail, > 40 chars). The picker must skip it and emit a clean line, or fall through to `"Quiet night."` if all candidates fail.
- [ ] 2.3 Verify the script runs in < 100 ms (sanity check that it stays fast).

## 2a. Bucket template sensor + automation rewrite

- [ ] 2a.1 New `ha/sensors/poetic_weather_bucket.yaml` defining `sensor.inkplate_night_poetic_bucket` with the existing bucket template logic.
- [ ] 2a.2 Rewrite `ha/automations/poetic_weather.yaml`: drop the hourly `time_pattern` trigger; add a `state` trigger on `sensor.inkplate_night_poetic_bucket` (with `not_to: [unknown, unavailable]`); keep `homeassistant.start` as a safety re-publish; gate by `input_boolean.inkplate_publisher_enabled`.
- [ ] 2a.3 Action passes the sensor's current value as the `bucket:` data field.
- [ ] 2a.4 Smoke: deploy, force a state change on the underlying weather entity (Developer Tools → Set State), confirm the bucket sensor flips, automation fires once, picker writes a new line.

## 3. Cleanup

- [ ] 3.1 Delete `ha/config/poetic_weather_line.yaml` (provider/model config no longer read).
- [ ] 3.2 Confirm `ha/secrets.yaml`'s `anthropic_api_key` is still used by `generate_astro_event.py` — do NOT remove the key.

## 4. Spec deltas

- [x] 4.1 `openspec/changes/replace-poetic-llm-with-pool/specs/ha-integrations/spec.md` — MODIFIED requirement: poetic-line generation pipeline.

## 5. Validation

- [ ] 5.1 `openspec validate replace-poetic-llm-with-pool` exits 0.
- [ ] 5.2 `ha/deploy.sh` succeeds after the changes.
- [ ] 5.3 Manually invoke `service: shell_command.generate_poetic_weather_line` with `bucket: clear_cold` from HA Developer Tools. Confirm `state/poetic_weather.txt` mtime updates and content is from the `clear_cold` bucket.
- [ ] 5.4 Confirm `sensor.inkplate_poetic_weather_line` updates within `scan_interval` (300 s default) of the file change.
- [ ] 5.5 Wait for the natural hourly trigger to fire and confirm the rendered Night face shows a valid English line.
