# Tasks — add-now-playing-ha-start-reconcile

## 1. HA automation

- [x] 1.1 `ha/automations/now_playing_override.yaml`: add a sibling automation `inkplate_sonos_ha_start_reeval` modeled on `inkplate_sonos_quiet_hours_end_reeval`. Trigger: `homeassistant.start`. Conditions: `media_player.kitchen_sonos == 'playing'` AND `input_text.inkplate_active_override != 'now_playing'` AND quiet-hours guard. Action: save prior_override, set override = now_playing, cancel linger timer, set now_playing_content_id from current Sonos media, publish `active_mode = now-playing` retained, publish wake pulse.

## 2. Spec delta

- [x] 2.1 `openspec/changes/add-now-playing-ha-start-reconcile/specs/now-playing-override/spec.md` — ADD Requirement "HA-start reconciliation" with one Scenario.

## 3. Validation

- [x] 3.1 `openspec validate add-now-playing-ha-start-reconcile --strict` exits 0.
- [x] 3.2 `ha/deploy.sh` validates HA core and restarts cleanly (no automation parse errors).
- [x] 3.3 Live verification:
  - Start Sonos session via phone (or any source). Confirm override = `now_playing`.
  - Restart HA via deploy. Wait for HA to come back.
  - Confirm: within seconds of HA-start, override remains / returns to `now_playing` (whether or not Sonos cycled `unavailable` mid-restart). Mirror catches up on next device wake.

## 4. Archive

- [x] 4.1 After live verification passes, archive via `openspec archive add-now-playing-ha-start-reconcile`.
