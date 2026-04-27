## 1. Renderer endpoint

- [x] 1.1 Add `POST /inputs/:name` handler in `renderer/src/server.ts`: validates `:name` against `^[a-z0-9_-]+$`, checks `Authorization: Bearer <token>` against `RENDERER_INPUT_TOKEN` env var, parses JSON body (413 if >256 KB), writes `RENDERER_INPUTS_DIR/<name>.json.tmp`, `fs.rename` to `<name>.json`. Returns `204` on success, `401/403/413/400` as appropriate.
- [x] 1.2 Add the token to `renderer/launchd/com.inkplate.renderer.plist` via a new `RENDERER_INPUT_TOKEN` env entry (operator fills in during deploy); document in `renderer/README.md`.
- [x] 1.3 Reject writes for any `name` not in the mode-input allow-list (`clock | weather | climate | hn | pairing | sonos | device`) — this keeps the endpoint from being a generic file-drop.
- [x] 1.4 Add a small integration test in `renderer/test/` that POSTs a valid clock payload, confirms the file exists on disk, and confirms `GET /display/summary.png` reflects the new value. — `renderer/test/inputs-endpoint.test.ts`, 6/6 pass.

## 2. Renderer schema: device input + battery removal from climate

- [x] 2.1 Add `deviceInput` to `renderer/src/modes/schema.ts`: `{battery: {percentage: number(0-100), voltage?: number}, build?: string, last_seen?: string}`.
- [x] 2.2 Remove `battery` from `climateInput.inside`. Update the doc comment.
- [x] 2.3 Add `device` to every mode's required-input set in `renderer/src/modes/*.ts` (`loadInputs` in each mode). Missing-input rule: `device.json` absent → skip, indicator renders em-dash (graceful degradation from `dashboard-faces`).
- [x] 2.4 Update `renderer/src/modes/summary.ts:57` to read `input.device.battery.percentage` instead of `input.climate.inside.battery`.
- [x] 2.5 Update `renderer/src/modes/{weather,gallery,nowPlaying,night}.ts` to pass `input.device?.battery?.percentage` instead of `undefined` to `batteryIndicator(...)`.
- [x] 2.6 Add `renderer/inputs/device.json` to the in-tree fixtures used by preview so `/display/*/preview` still works without HA attached.

## 3. HA rest_commands and automations

- [x] 3.1 Add `renderer_input_token` to `ha/secrets.yaml.example` and `ha/secrets.yaml`; document in `ha/docs/secrets-checklist.md`. — Stored as pre-composed `renderer_input_auth_header: "Bearer <token>"` (HA `!secret` can't compose a string from a secret + literal). Real `secrets.yaml` still needs the operator to replace `REPLACE_ME`.
- [x] 3.2 Register five `rest_command`s in `ha/integrations/rest_commands.yaml` (new file): `publish_clock`, `publish_weather`, `publish_climate`, `publish_hn`, `publish_device`. Each POSTs to `http://{{renderer_host}}:{{renderer_port}}/inputs/<name>` with Bearer auth and a templated JSON body. — URLs stored as five `!secret renderer_publish_*_url` entries (same HA limitation).
- [x] 3.3 Add `ha/automations/publish_inputs.yaml`:
  - `publish_clock`: time_pattern every minute.
  - `publish_weather`: state trigger on any renderer-facing weather template sensor; time_pattern hourly safety re-publish.
  - `publish_climate`: state trigger on kitchen climate sensors (no-op until the sensor lands; automation is present and disabled via `condition: template` checking sensor availability). — Uses `sensor.kitchen_temperature` / `_humidity` from the existing Tado integration; availability-guard prevents the automation from firing when Tado is offline.
  - `publish_hn`: state trigger on `sensor.inkplate_hn_top5` attribute change.
  - `publish_device`: MQTT trigger on `inkplate/state/device`; also homeassistant.start trigger for initial publish.
- [x] 3.4 Add one-shot republish on HA start for all publishers so fresh HA boots push the full input set without waiting for individual triggers. — Every publisher automation has a `- platform: homeassistant / event: start` trigger.
- [x] 3.5 Add `input_boolean.inkplate_publisher_enabled` (default on) as a top-level guard in all five automations. Documented in `ha/docs/architecture.md` as the rollback switch.

## 4. Test fixtures and goldens

- [x] 4.1 Add `renderer/test/fixtures/device.json` to the default bundle. The `degraded/` bundle deliberately omits it to exercise the missing-input graceful-degradation path; `forms/` bundles only provide clock + pairing (battery optional).
- [x] 4.2 Remove `battery` from the climate fixtures. — Production `renderer/inputs/climate.json` stripped; test fixtures didn't carry battery.
- [x] 4.3 Re-seed goldens: `UPDATE_GOLDENS=1 npm test`. Expected diff: battery indicator now populated on Weather, Gallery, Night, Now-Playing. — Goldens re-seeded; 6/6 snapshot tests pass on subsequent runs.
- [x] 4.4 Add a snapshot-level assertion that every face's golden contains a non-em-dash battery label. — `renderer/test/battery-indicator.test.ts` scrapes `/display/{mode}/preview` HTML for `82%` on every face and verifies the em-dash fallback when `device.json` is absent. 6/6 pass.

## 5. Documentation

- [x] 5.1 `renderer/README.md`: add `device` to the per-mode input table; document `POST /inputs/:name` with auth, allow-list, and response codes.
- [x] 5.2 `ha/docs/architecture.md`: add an "Input publisher catalog" section enumerating the five writers, their triggers, and the retry/backoff (HA `rest_command` retries are zero by default — document that a failed write is logged but not retried until the next trigger).
- [x] 5.3 Update `ha/docs/secrets-checklist.md` with the `renderer_input_token` line.
- [x] 5.4 Update `ha/docs/troubleshooting.md` with a "stale renderer inputs" section: `stat renderer/inputs/*.json` on the Mac to spot writers that aren't firing.

## 6. Deploy and verify

- [ ] 6.1 Deploy HA config (`make deploy-ha`), restart renderer. — **requires live HAOS + operator filling `secrets.yaml`**
- [ ] 6.2 Walk through each face's simulation (`curl /display/*.png`) and confirm: clock within 60 s of wall-clock, weather ≤ 15 min stale, battery indicator populated on every face. — **requires live HAOS**
- [ ] 6.3 Kill renderer briefly, confirm HA's rest_command logs the 500/connection-refused errors but keeps running; restart renderer, confirm the next trigger re-lands the write. — **requires live HAOS**
- [ ] 6.4 Toggle `input_boolean.inkplate_publisher_enabled` off, confirm no more POSTs reach the renderer; toggle on, confirm writes resume on next trigger. — **requires live HAOS**

## 7. Integration with other in-flight changes

- [x] 7.1 Cross-check with `add-ha-integrations` §15 (end-to-end integration tasks still open): this change supplies the missing piece for tasks 15.1–15.2 ("Spot-check each face with real data from HA"). — `add-ha-integrations/tasks.md` §16 added as the dependency back-pointer.
- [x] 7.2 Cross-check with `improve-text-crispness` §3: golden re-seed here should happen before or in coordination with the crispness change's §3.1 to avoid two golden-seed passes. — This change re-seeded the goldens; `improve-text-crispness/tasks.md` §3.1 is now effectively satisfied through this pass.
