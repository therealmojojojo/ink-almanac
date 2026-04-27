# Tasks — Configurable tier boundaries

## 1. HA helpers and validator

- [ ] 1.1 Add four `input_datetime` helpers (`inkplate_morning_start`, `inkplate_midday_start`, `inkplate_evening_start`, `inkplate_night_start`) to `ha/integrations/helpers.yaml` with the current defaults
- [ ] 1.2 Add a Jinja validator template (monotone + min-width 30 min) in a shared location callable from the publisher

## 2. HA publisher

- [ ] 2.1 Add `ha/automations/tier_boundaries.yaml` mirroring `sleep_strategy.yaml`'s shape (state-change triggers + HA-start trigger)
- [ ] 2.2 Validator gate: refuse to publish when validator returns false; log warning; notify via existing channel
- [ ] 2.3 Publish `inkplate/command/tier_boundaries` retained on every successful validation
- [ ] 2.4 First-install bootstrap: publish defaults on HA start when the retained topic is absent

## 3. HA Jinja consumers

- [ ] 3.1 Rewrite `ha/automations/schedule.yaml` to source tier boundaries from `input_datetime.inkplate_*_start` instead of literals
- [ ] 3.2 Rewrite `ha/automations/gesture_override.yaml` (`tap-during-schedule` and `tap-during-now-playing` both compute tier from the same boundaries) to source from helpers
- [ ] 3.3 Confirm the alternation tick (every 15 min) still produces the expected face when a boundary is shifted mid-day

## 4. Firmware — Persisted RTC field

- [ ] 4.1 Add four `uint16_t` fields (`morning_start_min`, `midday_start_min`, `evening_start_min`, `night_start_min`) to `Persisted` in `firmware/include/wake.h`
- [ ] 4.2 Document the zero-sentinel meaning ("unset → use compile-time defaults") inline

## 5. Firmware — boundary reader

- [ ] 5.1 Add `wake::TierBoundaries effectiveBoundaries()` returning either the cached values or `kDefaultBoundaries`
- [ ] 5.2 Rewrite `tierFor()` to compare `min_of_day` against `effectiveBoundaries()` instead of literals
- [ ] 5.3 Keep `kDefaultBoundaries` as the same constants used today (390 / 600 / 1020 / 1320) so a device with no MQTT update behaves identically

## 6. Firmware — MQTT subscriber

- [ ] 6.1 Extend the existing per-wake `mqttReadRetained` step in `main_loop.cpp` to also read `inkplate/command/tier_boundaries`
- [ ] 6.2 Parser: accept JSON `{morning_start, midday_start, evening_start, night_start}` as `HH:MM` strings; convert to minute-of-day integers
- [ ] 6.3 Validator: monotone + min-width 30 min; reject and log on failure (same shape as `fetchAndStoreClockZone`'s error path)
- [ ] 6.4 On valid payload: write to `Persisted` RTC fields

## 7. Firmware — tests

- [ ] 7.1 `schedule_tests.cpp`: regression — default cache → existing behavior unchanged across all four tier boundary scenarios
- [ ] 7.2 `schedule_tests.cpp`: shifted-boundary cache → minute that was Morning is now Night (or vice versa); confirms `tierFor` actually consults the cache
- [ ] 7.3 `schedule_tests.cpp`: zero-sentinel cache → falls back to defaults
- [ ] 7.4 New host-test scenario: simulate `inkplate/command/tier_boundaries` payload, run a tick, assert `Persisted` updated; second test: malformed payload, assert `Persisted` untouched

## 8. Documentation

- [ ] 8.1 Update `firmware/docs/wake-protocol.md § Refresh schedule` — note that boundaries are now runtime-configurable; add the new MQTT topic to the topics table
- [ ] 8.2 Update `firmware/docs/config.md § Schedule planner constants` — mark boundaries as fallback values (cadences remain `constexpr`)
- [ ] 8.3 Update `ha/docs/sleep-strategy.md` to include the new helpers in the helpers table (or add a sibling `tier-boundaries.md` if the table grows too large)
- [ ] 8.4 Cross-link from `HOWTO.md § Customize the schedule` (replace "edit `wake.cpp` and `schedule.yaml` in lockstep" with "edit the four helpers in HA").

## 9. Acceptance

- [ ] 9.1 Boot a device with no `tier_boundaries` topic published — schedule behaves identically to today
- [ ] 9.2 Publish a shifted Morning start (e.g. 07:00); within one wake, firmware logs reflect the new boundary; HA's alternation tick computes the new tier on next fire
- [ ] 9.3 Publish an invalid payload (Morning > Midday); HA validator refuses publish; previously valid payload remains; firmware unaffected
- [ ] 9.4 Force-publish an invalid payload by hand (bypassing HA validator); firmware logs the parse failure and continues with last-good values
- [ ] 9.5 Documentation changes reviewed; no remaining references to the literal minute-of-day boundaries except in `kDefaultBoundaries` and `firmware/docs/config.md` defaults table
