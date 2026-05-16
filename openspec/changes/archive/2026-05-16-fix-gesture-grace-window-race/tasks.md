# Tasks — Fix the IMU gesture grace-window race

## 1. Firmware — protocol constants

- [x] 1.1 `firmware/include/config.h`: add `inline constexpr const char* kTopicGestureResponse = "inkplate/command/gesture_response";` next to `kTopicActiveMode`. Align column widths in the surrounding block for readability.

## 2. Firmware — IMU branch

- [x] 2.1 `firmware/src/main_loop.cpp`: in the IMU branch of `doFull` (around line 439, the `if (reason == wake::Reason::IMU && ...)` clause), change the `mqttWaitForMessage` target from `kTopicActiveMode` to `kTopicGestureResponse`. Update the surrounding comment to explain the state-vs-event topic split.
- [x] 2.2 Same branch, on timeout (`payload.empty()`): fall back to `active = resolveActiveMode(h.transport, local_hour);`. Comment the why — preserves the "HA changed `active_mode` mid-sleep, tap also picks it up" behavior that the pre-fix racy code accidentally provided.

## 3. Firmware — transport doc contract

- [x] 3.1 `firmware/src/hal/real/RealTransport.h::mqttWaitForMessage`: update the doc comment to state the contract — "intended for non-retained event topics; on a retained topic the broker would replay the stored value on subscribe and the wait would short-circuit on it, defeating the purpose."

## 4. Test harness — mock transport

- [x] 4.1 `firmware/test/hal/mock/MockTransport.h`: add a `pending_push_` map keyed by topic. Update the class-level doc comment to describe the new "retained-or-recent-push" semantics.
- [x] 4.2 `firmware/test/hal/mock/MockTransport.cpp::mqttPublish`: when `retained == false`, store the payload into `pending_push_[topic]`. Retained publishes continue to land in `retained_` only.
- [x] 4.3 `firmware/test/hal/mock/MockTransport.cpp::mqttWaitForMessage`: prefer `retained_[topic]` when present; otherwise drain and return `pending_push_[topic]`; otherwise empty. Drain-on-read so a second wait without a fresh push returns empty.

## 5. Tests — IMU scenarios

- [x] 5.1 `firmware/test/scenarios/main_loop_tests.cpp` "IMU wake: gesture published before active_mode resolved": publish hook now publishes `kTopicGestureResponse` non-retained alongside `kTopicActiveMode` retained. Comment updated.
- [x] 5.2 Same file, "IMU wake during quiet hours: HA holds Night, no face change": replace the publish hook with an empty hook. With no `gesture_response` push, the device times out and falls back to `resolveActiveMode`, which reads the (still-retained) `active_mode = night` and renders Night unchanged.
- [x] 5.3 Same file, "IMU wake: double tap gesture payload": publish hook now publishes both topics.
- [x] 5.4 Verify the existing "IMU wake: HA silent → keep pre-gesture face" test still passes — no hook installed, so neither topic gets a fresh push, the wait times out, the fallback reads retained `active_mode = summary` (same as the persisted current mode), and the device renders Summary. The full refresh still happens because Inkplate 10's partial path is a no-op in 3-bit.

## 6. HA — gesture handlers

- [x] 6.1 `ha/automations/gesture_override.yaml::inkplate_gesture_tap_phase_flip` action block: prepend a non-retained `mqtt.publish` to `inkplate/command/gesture_response` with the same `flip_face` payload as the existing retained `active_mode` publish. Comment-block above the new step explains the contract.
- [x] 6.2 `ha/automations/gesture_override.yaml::inkplate_gesture_tap_now_playing_peek` action block: same — prepend a non-retained `mqtt.publish` to `inkplate/command/gesture_response` with the `peek_face` payload.
- [x] 6.3 (Optional) `ha/automations/gesture_override.yaml::inkplate_gesture_tap_now_playing_peek` revert step (after the 60-s delay): consider also publishing `gesture_response = now-playing` for symmetry. **Decision: skip.** The revert isn't tap-driven — there's no IMU wake waiting on the grace window — so the retained `active_mode = now-playing` plus the next Poll's mode-change detection is sufficient.

## 7. Docs

- [x] 7.1 `ha/docs/architecture.md` — add `inkplate/command/gesture_response` to both MQTT topic tables (the long-form and the short-form). Add a paragraph below the long-form table explaining the state-channel/event-channel split and why the IMU grace window listens on the event channel.

## 8. Spec deltas

- [x] 8.1 `openspec/changes/fix-gesture-grace-window-race/specs/device-firmware/spec.md` — MODIFIED Requirement: Tap detection. Restate the full requirement reflecting the gesture_response topic, the timeout fallback to `resolveActiveMode`, and updated scenarios. The HA-side publishing contract is captured implicitly in the requirement's narrative (HA publishes on two topics) — the canonical `ha-integrations` spec doesn't currently carry a gesture-handler requirement to modify, so introducing one here would expand scope unnecessarily.

## 9. Validation

- [x] 9.1 `openspec validate fix-gesture-grace-window-race` exits 0.
- [x] 9.2 Host suite passes: `cd firmware && cmake --build build_host -j && ./build_host/firmware_sim` exits 0 with all 97 tests passing.

## 10. Deployment

- [x] 10.1 Deploy HA: `cd ha && ./deploy.sh`. Confirm `gesture_override.yaml` lands on the HAOS VM. Verify by running `ha core check` on the VM and watching the gesture automation traces in HA's UI.
- [x] 10.2 Flash firmware: PlatformIO OTA. Confirm next IMU wake's `state/device` JSON shows the right `active_mode` (matching the tapped face) within ~10 s of a tap during schedule hours. (Shipped in the same binary as `fix-active-mode-fallback` — commit `3295b28` landed before `334bacf` and both fixes are present in build `0.8.1-active-mode-fallback`.)
- [x] 10.3 Live verification: tap during a Summary slot, confirm Weather renders within ~10 s. Repeat: tap during a Weather slot, confirm Summary renders. Repeat during a now-playing peek to confirm peek path also works. (Operator-verified across ~1 week of normal use; tap-during-Summary reliably switches to Weather.)
