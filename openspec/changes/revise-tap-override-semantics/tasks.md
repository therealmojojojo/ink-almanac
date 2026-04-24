# Tasks — revise-tap-override-semantics

## 1. HA — gesture handler

- [x] 1.1 Drop `!= 'now_playing'` condition on `inkplate_gesture_single_tap`
- [x] 1.2 Add self-overwrite guard on `inkplate_gesture_single_tap`'s prior-save step
- [x] 1.3 Add self-overwrite guard on `inkplate_gesture_double_tap`'s prior-save step
- [x] 1.4 Replace `inkplate_weather_peek_expiry` restore block with the unified cascade
- [x] 1.5 Add `inkplate_ha_start_stale_peek_cleanup` automation
- [x] 1.6 Update file-header comment block to document activation model and invariants

## 2. HA — Sonos / linger handler

- [x] 2.1 Add `active_override == now_playing` condition on `inkplate_sonos_linger_expired`
- [x] 2.2 Replace linger restore block with the unified cascade

## 3. HA — helpers

- [x] 3.1 `inkplate_weather_peek_seconds.initial: 300 → 60`; refresh comment
- [x] 3.2 Update `inkplate_active_override` comment to reflect activation/deactivation split
- [x] 3.3 Document `prior != active` invariant on `inkplate_prior_override`

## 4. Documentation

- [x] 4.1 Rewrite "Override precedence" → "Activation model and deactivation precedence" in `architecture.md`
- [x] 4.2 Rewrite the face-selection state-machine diagram to show per-event activation + shared restore cascade
- [x] 4.3 Update HA-state helper listing to include the peek-expiry and peek-seconds helpers and note the prior invariant

## 5. Validation

- [ ] 5.1 `make deploy-ha` on operator machine
- [ ] 5.2 Manually exercise via web sim (sentinel.mjjj.space/sim):
  - [ ] Play music → tap single → weather visible ~60–120 s → auto-returns to now-playing (music still playing)
  - [ ] Play music → tap single → pause music during peek → peek expires → falls through to schedule (not now-playing)
  - [ ] Play music → tap double → suppressed (no state change)
  - [ ] Pause music → tap single during linger window → weather peek → linger fires but is a no-op → peek expiry restores per cascade
  - [ ] In weather_peek → tap single again → peek timer resets, prior unchanged
  - [ ] In summary_gallery_toggle → tap double → face re-toggles, prior unchanged
- [ ] 5.3 HA-restart stale-peek: manually set `inkplate_active_override = weather_peek` and `inkplate_weather_peek_expires_at` to a past time; restart HA; verify startup cleanup fires
- [ ] 5.4 Verify deploy logs clean, `ha core check` passes

## 6. Archival

- [ ] 6.1 Merge capability delta into `openspec/specs/ha-override-state/` (new capability spec)
- [ ] 6.2 `openspec validate revise-tap-override-semantics`
- [ ] 6.3 Archive
