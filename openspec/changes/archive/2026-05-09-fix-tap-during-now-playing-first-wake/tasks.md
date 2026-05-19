# Tasks — fix-tap-during-now-playing-first-wake

## 1. HA automations

- [x] 1.1 `ha/automations/gesture_override.yaml`: split the now-playing-tap handler into two automations:
  - `inkplate_gesture_tap_now_playing_first_wake` (new, `mode: single`): triggers on single+double, conditions `override == now_playing` AND `sensor.inkplate_commanded_face != 'now-playing'` AND not-quiet-hours. Action: publish `inkplate/command/gesture_response = now-playing` non-retained. Nothing else.
  - `inkplate_gesture_tap_now_playing_peek` (modified, `mode: restart` retained): add condition `sensor.inkplate_commanded_face == 'now-playing'`. Replace `peek_face` template with literal `weather`. Update the inline comment block to describe the two-handler split and why the mirror is the discriminator.

## 2. Operator docs

- [x] 2.1 `ha/README.md` — replace the "Tap during now_playing" line under "Gesture handler" with two lines: first wake confirms now-playing, subsequent tap peeks to weather for 60 s.

## 3. Spec delta

- [x] 3.1 `openspec/changes/fix-tap-during-now-playing-first-wake/specs/now-playing-override/spec.md` — ADD Requirement "Tap interaction during now-playing" with three Scenarios (first wake confirms now-playing, subsequent tap peeks to weather, tap during peek returns to now-playing).

## 4. Validation

- [x] 4.1 `openspec validate fix-tap-during-now-playing-first-wake --strict` exits 0.
- [x] 4.2 `ha/deploy.sh` validates HA core and restarts cleanly (no automation parse errors).
- [x] 4.3 Live verification on the operator's device (2026-05-09 — operator confirmed; one false-start because the deploy's HA restart had stranded `inkplate_active_override` on `schedule` while Sonos was playing, masked by an `unavailable` Sonos state mid-restart; fixed by manually triggering `inkplate_sonos_started_activate_now_playing`. Follow-up to add `homeassistant.start` trigger tracked in a sibling change):
  - Start Sonos session.
  - Wait for device to go to sleep without drawing now-playing (i.e. screen on weather/gallery/summary from prior tier).
  - Double-tap. Confirm: device wakes, draws now-playing.
  - Double-tap again. Confirm: device draws weather (60 s peek).
  - Double-tap during the peek. Confirm: device draws now-playing.
  - Wait 60 s after the last "stay on now-playing" tap. Confirm: nothing happens (device is asleep, peek timer's revert is a no-op).

## 5. Archive

- [ ] 5.1 After live verification passes, merge the spec delta into `openspec/specs/now-playing-override/spec.md` and archive the change directory under `openspec/changes/archive/`.
