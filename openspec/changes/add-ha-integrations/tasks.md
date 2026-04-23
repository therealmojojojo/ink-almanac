## 1. Repo scaffolding

- [x] 1.1 Create `ha/` directory with `automations/`, `sensors/`, `scripts/`, `config/`, `state/`
- [x] 1.2 Create `ha/secrets.yaml.example` with placeholder keys and a clear structure
- [x] 1.3 Add `.gitignore` rules for `ha/secrets.yaml` and `ha/state/`
- [x] 1.4 Write `ha/README.md` covering setup, deploy, per-file purpose

## 2. Deploy mechanism

- [x] 2.1 Install HA SSH & Web Terminal add-on on the HAOS VM; configure operator's public key — **operator done; deploying on port 2222 against ${HA_HOST}**
- [x] 2.2 Write `ha/deploy.sh`: verify SSH, rsync `ha/` → `/config/custom/inkplate/` on the VM, trigger HA reload via SSH
- [x] 2.3 Add `deploy-ha` target to the top-level Makefile
- [x] 2.4 First deploy round-tripped cleanly: tar-over-ssh transfer (rsync unavailable on add-on), `ha core check` + `ha core restart`, all inkplate-derived sensors populated

## 3. Weather integration

- [x] 3.1 MET.no config entry for ${PLACE_A_NAME} created via REST API config-flow; entity renamed to `weather.${PLACE_A_SLUG}_primary`. YAML `weather: - platform: met` dropped (HA 2024.4+ refuses it)
- [x] 3.2 Same for ${PLACE_B_NAME} → `weather.${PLACE_B_SLUG}_primary`
- [x] 3.3 ~~Fallback provider~~ — **DROPPED**. MET.no only; OWM fallback removed per operator decision (simpler, no extra key, acceptable degradation when MET.no is unreachable).
- [x] 3.4 Create template sensors exposing renderer inputs per location (temp, condition, H/L, rain, feels-like, 5-day forecast) — `ha/sensors/weather_template.yaml` (single-provider, no compositing)

## 4. Indoor climate

- [x] 4.1 ~~Identify/install the kitchen sensor~~ — **DEFERRED**. Operator opted out; indoor climate not shipped in this change.
- [x] 4.2 ~~Expose `sensor.kitchen_temperature` / `sensor.kitchen_humidity`~~ — **DEFERRED**. `ha/sensors/kitchen_climate.yaml` deleted. The Summary climate zone will render empty until a sensor is added in a future change; the `Indoor climate` requirement in the spec is effectively waived for this deploy.

## 5. Sonos

- [x] 5.1 Configure the native Sonos integration; identify the kitchen speaker's entity id — **operator done**
- [x] 5.2 Rename/alias the entity to `media_player.kitchen_sonos` — **operator done (entity name set directly)**
- [x] 5.3 Verified attributes exposed during Spotify playback: `state`, `media_content_id`, `media_title`, `media_artist`, `media_album_name`, `entity_picture`. `source` absent under Spotify (expected) — spec relaxed to make it optional; renderer derives label from `media_content_id` prefix.
- [x] 5.4 Wire the `now-playing-override` helpers (coordinate with `add-now-playing-mode`) — helpers + linger-timer + MQTT bridge shipped in `ha/integrations/helpers.yaml` and `ha/automations/now_playing_override.yaml`

## 6. News sources

- [x] 6.1 Implement HN REST sensor (refresh 30 min, top 5 stories) — `ha/sensors/hn.yaml` + `ha/scripts/fetch_hn_top.sh`
- [x] 6.2 Create `ha/config/news_sources.yaml` with HN and at least one Romanian source — digi24 + hotnews shipped (HN kept separate due to chained-fetch shape)
- [x] 6.3 Implement a loader that generates per-source sensors from the YAML at deploy time — `ha/scripts/generate_news_sensors.py`, invoked from `deploy.sh`

## 7. Astro

- [x] 7.1 `sun` auto-loads via `default_config:`; `moon` config entry created via REST API (YAML `sensor: platform: moon` refused in 2025+); `homeassistant:` coordinate block dropped from package (packages only allow `customize` there)
- [x] 7.2 Template sensors for sunrise, sunset, daylight duration, moon-phase name live. `next_full_moon_date` returns `unknown` — 2026.x Moon integration doesn't expose that attribute; renderer treats as optional
- [x] 7.3 Astro-event sensor rewritten as a `command_line` sensor calling `fetch_astro_event.sh` (the YAML `scrape` platform also lost platform-setup support)

## 8. Scheduled-mode automation

- [x] 8.1 Implement 06:30 / 10:00 / 22:00 triggers — `ha/automations/schedule.yaml`
- [x] 8.2 Each trigger: consult `input_text.active_override`; if `schedule`, update the scheduled face and wake the device
- [x] 8.3 Each trigger: if higher-precedence override is active, update the internal "current scheduled face" but do NOT wake the device — scheduled_face helper always updated; wake gated on override=schedule
- [x] 8.4 HA-side chain verified live: automation loaded (state=on), helpers update on `input_text.set_value`, `mqtt.publish` lands with `retain=true`, `inkplate/command/active_mode=summary` visible on the broker via HA websocket MQTT subscribe. Device-side ack of the wake pulse still pending firmware.

## 9. Pairing-generation trigger

- [x] 9.1 Register `shell_command.generate_pairings_week` pointing to `corpus pair generate-week` — `ha/integrations/shell_commands.yaml` → `ha/scripts/generate_pairings_week.sh`
- [x] 9.2 Create Sunday 23:30 automation calling the shell command — `ha/automations/pairings.yaml`
- [x] 9.3 On success, send a notification; on failure, send a failure notification — success + failure branches in `pairings.yaml`
- [ ] 9.4 Verify manually and via dry-run — **requires live HAOS + `corpus` CLI on renderer host** (the CLI itself is `add-corpus-ingestion`, not yet shipped)

## 10. Poetic-weather-line automation

- [x] 10.1 Create `ha/config/poetic_weather_line.yaml` with provider, model, cache-file path
- [x] 10.2 Create `ha/config/night_fallback_lines.yaml` with ~50 lines across weather buckets — 48 lines across 8 buckets (≥6 per bucket)
- [x] 10.3 Implement the hourly automation (conditional on Night-mode hours) — `ha/automations/poetic_weather.yaml` + `ha/scripts/generate_poetic_weather_line.sh` (validation, fallback, Claude + Ollama providers)
- [x] 10.4 HA-side verified: `shell_command.generate_poetic_weather_line` runs, `/config/custom/inkplate/state/poetic_weather.txt` written with a valid ≤32-char line ("Soft cloud, no stars.") from the fallback pool. **Note:** fallback fired because HA's `shell_command` doesn't inject `ANTHROPIC_API_KEY` into the process env — Claude path untested until secret is wired through (see §16.1 follow-up). Renderer round-trip still pending renderer.

## 11. Low-battery notification

- [x] 11.1 Consume the battery-percentage entity exposed by `add-device-firmware` — `sensor.inkplate_device_battery` in `ha/integrations/mqtt.yaml`
- [x] 11.2 Implement threshold trigger at <20% with 4-hour throttle — `ha/automations/low_battery.yaml`
- [x] 11.3 Send to operator's phone via HA mobile app notification — via `notify.inkplate_operator` group aliased in `ha/integrations/notify.yaml`

## 11b. Sleep-strategy helpers

- [x] 11b.1 Create `input_datetime.sonos_active_start` (07:00 default) and `input_datetime.sonos_active_end` (20:00 default) — in `ha/integrations/helpers.yaml`
- [x] 11b.2 Create `input_datetime.quiet_start` (00:00 default) and `input_datetime.quiet_end` (05:00 default)
- [x] 11b.3 Create `input_number.fast_path_interval_seconds` (180 default, 60–600 range)
- [x] 11b.4 Automation: on any sleep-strategy helper change, publish the full strategy bundle to a retained MQTT topic (e.g., `inkplate/command/sleep_strategy`) — `ha/automations/sleep_strategy.yaml` (also republishes on HA start)
- [x] 11b.5 Document the defaults and their rationale in `ha/docs/sleep-strategy.md`

## 12. Override state helpers

- [x] 12.1 Create `input_text.active_override` with allowed values as documented — `input_text.inkplate_active_override` in `ha/integrations/helpers.yaml`
- [x] 12.2 Create `input_text.prior_override` — `input_text.inkplate_prior_override`
- [x] 12.3 Document the state semantics in `ha/README.md`
- [ ] 12.4 Verify `now-playing-override` scenarios read and write these correctly — **depends on `add-now-playing-mode` + live HAOS**

## 13. Secrets

- [x] 13.1 Collect all required credentials (weather, LLM, HN if authenticated, any others) — inventory in `ha/docs/secrets-checklist.md`; template in `ha/secrets.yaml.example`
- [x] 13.2 `ha/secrets.yaml` populated (anthropic key rotated twice + now live, coordinates, mqtt_broker_host=${HA_HOST}, renderer_host=${RENDERER_HOST}, operator_notify_service=mobile_app_cs_phone)
- [x] 13.3 Deployed. `ha core check` passes. Only `!secret` reference in the fragment tree is `operator_notify_service`, which resolves. Every other secret is consumed by shell scripts, not by HA's `!secret` resolver.

## 14. Documentation

- [x] 14.1 Write `ha/docs/architecture.md` showing the automations, state, and data flow
- [x] 14.2 Write `ha/docs/deploy.md` covering SSH setup, deploy command, rollback
- [x] 14.3 Write `ha/docs/troubleshooting.md` with common failure modes

## 14b. Pre-deploy hardening (review fixes)

- [x] 14b.1 `shell_commands.yaml` wrapped under top-level `shell_command:` so it loads as a package fragment; duplicate `!include` removed from `deploy.md` and `README.md`
- [x] 14b.2 `deploy.sh` uses `ha core check && ha core restart` (supervisor CLI has no `ha core reload`); rsync uses a generated SSH wrapper so key paths with spaces don't break via IFS join
- [x] 14b.3 `weather_template.yaml` `forecast` attribute now emits a real list of projected dicts via a namespace loop instead of a stringified JSON blob; fallback rule unified across all fields
- [x] 14b.4 `fetch_rss.sh` / `fetch_json.sh` / `fetch_hn_top.sh` pipe untrusted network payloads to Python via stdin instead of embedding them in `"""..."""` literals; smoke-tested with a hostile feed
- [x] 14b.5 `generate_poetic_weather_line.sh` builds JSON request bodies with `jq -n --arg` and passes untrusted values via env, not heredoc interpolation; candidate validation runs on stdin
- [x] 14b.6 `schedule.yaml` collapsed from three near-identical automations to one trigger-id-driven automation
- [x] 14b.7 Deploy transport switched from rsync to tar-over-ssh (HA SSH add-on doesn't ship rsync)
- [x] 14b.8 Forecast sensors moved to a trigger-based `template:` package calling `weather.get_forecasts` hourly; HA removed the static `forecast` attribute in 2024.4+
- [x] 14b.9 `generate_poetic_weather_line.sh`: reads `ANTHROPIC_API_KEY` from the deployed secrets.yaml when HA's `shell_command` doesn't inject env vars; replaced `jq` (not in HA Core container) with stdlib `python3 -c`; fixed a `python3 - <<PY` pattern that was eating stdin so `extract_text` received empty input. Claude path verified end-to-end against live API.

## 15. Integration

- [ ] 15.1 Verify every spec scenario passes end-to-end — **requires live HAOS + device + renderer**
- [ ] 15.2 Spot-check each face with real data from HA: Summary, Weather, Gallery (both flavors), Night (with poetic line), Now-Playing — **requires live HAOS + device**
- [ ] 15.3 Run for one full 24-hour cycle and review: do all transitions fire cleanly, do overrides behave, do notifications trigger? — **requires live HAOS + device + 24h**

## 16. Renderer integration (split out — see companion change)

> The HA→renderer input publisher layer (clock, weather, climate, hn, device state)
> is specified in `openspec/changes/add-ha-renderer-input-bridge/`. That change owns
> the `POST /inputs/:name` endpoint, the five `rest_command`s, the driving automations,
> and the `renderer_input_token` secret. Tasks 15.1–15.2 above cannot be checked `[x]`
> until the bridge change ships, because without publishers the renderer serves stale
> fixtures.

- [ ] 16.1 Track `add-ha-renderer-input-bridge` as a blocker for §15 sign-off.

## 17. Kitchen-motion integration (split out — see companion change)

> Motion detection has moved off-device to an IKEA sensor reporting via HA Zigbee/Matter.
> Specified in `openspec/changes/move-pir-to-ha-motion/`. That change adds the
> `kitchen_motion_wake` and `kitchen_motion_battery` automations and removes the
> device-side PIR path. Tasks 15.1–15.3 above implicitly cover the motion scenario
> once that change ships.

- [ ] 17.1 Track `move-pir-to-ha-motion` as a parallel dependency for §15 sign-off.
