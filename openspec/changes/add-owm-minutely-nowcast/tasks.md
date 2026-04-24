# Tasks — add-owm-minutely-nowcast

## 1. Secrets

- [x] 1.1 Add `openweathermap_api_key` to `ha/secrets.yaml` with real key
- [x] 1.2 Add `openweathermap_api_key` placeholder to `ha/secrets.yaml.example`

## 2. HA integration

- [x] 2.1 Rewrite `ha/integrations/weather_nowcast_minutely.yaml` to use OWM OneCall 3.0
- [x] 2.2 Rename rest sensors `*_openmeteo_minutely` → `*_owm_minutely`
- [x] 2.3 Update template sensors to parse OWM's `minutely[]` array (1-min buckets)
- [x] 2.4 Combiner sensors unchanged (still read `*_nowcast_minutely_label` with hourly fallback)

## 3. Renderer

- [x] 3.1 Add `.nowcast` div to `renderer/src/modes/weather.ts`'s `renderRow`
- [x] 3.2 Add matching `.weather-row .current .nowcast` CSS rule
- [x] 3.3 Confirm Summary face nowcast rendering unchanged (no edit needed)

## 4. Documentation

- [x] 4.1 `ha/docs/secrets-checklist.md` — `openweathermap_api_key` row marked "always"
- [x] 4.2 `ha/docs/architecture.md` — component diagram updated
- [x] 4.3 Proposal explicitly addresses the older "DROPPED" OWM fallback decision

## 5. Validation

- [x] 5.1 `ha core check` passes in the deploy
- [x] 5.2 `sensor.${PLACE_A_SLUG}_owm_minutely` state `ok:60` with 60 `minutely` buckets
- [x] 5.3 `sensor.${PLACE_B_SLUG}_owm_minutely` state `ok:60` with 60 `minutely` buckets
- [x] 5.4 Synthetic wet-data template test produces "RAIN IN 8 MIN" correctly
- [x] 5.5 `renderer/inputs/weather.json` carries `nowcast.label` per location
- [x] 5.6 Weather face preview HTML includes `<div class="nowcast">...</div>` per row
- [ ] 5.7 Live rain-forecast cycle (wait for actual precipitation, verify label transitions NOW → CLEARING → empty)

## 6. Archival

- [ ] 6.1 Merge deltas into `openspec/specs/ha-integrations/` and `openspec/specs/dashboard-faces/` (when those specs are ratified)
- [ ] 6.2 `openspec validate add-owm-minutely-nowcast`
- [ ] 6.3 Archive
