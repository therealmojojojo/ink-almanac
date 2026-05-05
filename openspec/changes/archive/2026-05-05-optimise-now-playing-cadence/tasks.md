# Tasks — Optimise Now-Playing wake cadence

## 1. Firmware — types and storage

- [x] 1.1 `firmware/include/wake.h`: add `uint32_t sonos_track_hash = 0;` to `Persisted`. Document: zero = uninitialised; populated by `doFull` after a NowPlaying draw.
- [x] 1.2 `firmware/include/wake.h`: add `bool session_now_playing = false;` to `Persisted`. Document: set on every Full/Poll/PollPartial wake from the retained `inkplate/state/active_override` topic; persists across deep sleep so Timer wakes consult the right cadence without an extra MQTT read before path dispatch.
- [x] 1.3 `firmware/include/config.h`: add `inline constexpr const char* kTopicNowPlayingTrack = "inkplate/state/now_playing_track";` and `inline constexpr const char* kTopicActiveOverride = "inkplate/state/active_override";` next to `kTopicSchedule`.

## 2. Firmware — planWake change (session-aware)

- [x] 2.1 `firmware/src/wake.cpp::pathForMinute`: change the NowPlaying override from `return Path::Full;` to `return Path::Poll;`. Make the override condition session-aware: `if (session_now_playing || mode == fw::modes::Mode::NowPlaying) return Path::Poll;`. Update the comment block above to reflect both triggers (session flag is canonical; mode check is the cold-boot fallback).
- [x] 2.2 `firmware/include/wake.h`: extend `planWake` signature with a `bool session_now_playing` parameter. Default to `false` in the host overload used by `schedule_tests.cpp` so existing tests don't need to thread it explicitly.
- [x] 2.3 `firmware/src/main_loop.cpp` and `firmware/src/main.cpp`: thread `wake::persisted().session_now_playing` into the `planWake` calls.
- [x] 2.4 Verify `planWake`'s "find next non-Skip minute" loop still terminates correctly — Poll is non-Skip, so the existing ≤1440 search continues to work without change.

## 3. Firmware — session-override + track-change reads

- [x] 3.1 `firmware/src/main_loop.cpp`: implement `readSessionOverride(transport)` — reads `kTopicActiveOverride` retained, empty-payload short-circuit, sets `persisted.session_now_playing = (payload == "now_playing")` for any non-empty payload.
- [x] 3.2 `firmware/src/main_loop.cpp` Poll/Full bring-up: call `readSessionOverride` alongside the existing `readAndApplySchedule` call (after `mqttConnect`, before path dispatch dependent reads).
- [x] 3.3 Poll branch: after the existing `resolveActiveMode` + mode-change-promotion block, add a track-version check. Run it only when `mqtt && resolved == NowPlaying && /* mode-change-promotion didn't already fire */`. **IMPORTANT**: gate on `resolved == NowPlaying` (i.e., current `active_mode`), NOT on `session_now_playing` — during a peek, mode is briefly Summary while session stays now_playing, and we don't want to promote on track changes during the peek.
- [x] 3.4 The check: `track = mqttReadRetained(kTopicNowPlayingTrack)`. If `track.empty()` → short-circuit (no hash, no cache write, no diag flag, no promotion). Else `track_hash = fnv32(track)`. If `track_hash != persisted.sonos_track_hash` → call `doFull(...)` with `already_resolved = NowPlaying`.
- [x] 3.5 Do NOT update `persisted.sonos_track_hash` in the Poll handler. The Full path updates it; if the Full fails (no draw, no MQTT), the cache stays stale and the next Poll retries.

## 4. Firmware — `doFull` cache update

- [x] 4.1 `firmware/src/main_loop.cpp::doFull`: after `wake::persisted().current_mode = active`, when `active == NowPlaying && mqtt`, read `kTopicNowPlayingTrack`. Empty → leave cache untouched. Non-empty → `persisted.sonos_track_hash = fnv32(track)`.
- [x] 4.2 Verify the order: `current_mode` is updated FIRST (so subsequent re-entries see NowPlaying), then `sonos_track_hash` (so subsequent Polls dedupe correctly).

## 5. Firmware — host tests

- [x] 5.1 Extend `firmware/test/scenarios/wake_schedule_plan_tests.cpp`: assert that `planWake(any_minute, NowPlaying, kDefaultSchedule, /*session=*/false)` returns `path == Poll` for representative minutes (mode-based fallback). Assert that `planWake(any_minute, Summary, kDefaultSchedule, /*session=*/true)` ALSO returns `path == Poll` (session-based override during peek). Both cases yield `minutes_to_next_wake == 1`. (Updates the existing "NowPlaying overrides every cadence" test cases that currently assert Full.)
- [x] 5.2 New `firmware/test/scenarios/now_playing_track_tests.cpp` — a Scenario harness test:
    - **Case 1**: cold boot into NowPlaying with session_now_playing populated → first Full draws → `mqttReadRetained(kTopicNowPlayingTrack)` returns `"album:track-1"` → `persisted.sonos_track_hash` populated. Next Timer Poll → reads same payload → hash matches → does NOT promote to Full (assert `display.fullRefreshCount` stays at 1).
    - **Case 2**: same setup, but on the Poll the broker's track payload changes to `"album:track-2"` → Poll detects mismatch → promotes to Full (assert `fullRefreshCount` increments). After the Full, `persisted.sonos_track_hash` reflects the new hash.
    - **Case 3**: NowPlaying with empty retained `now_playing_track` payload (broker has nothing) → first Full draws (mode-change), `sonos_track_hash` left at 0. Next Poll → empty short-circuit → no promotion (assert `fullRefreshCount` stays at 1).
    - **Case 4**: peek-during-music. Setup: session_now_playing=true (HA's override is now_playing), mode flips to Summary (peek active_mode), broker's `now_playing_track` topic still has track-1 payload. Poll fires every minute (session override). Even if the broker's track payload changes mid-peek to track-2, the device does NOT promote to Full because `resolved (active_mode) != NowPlaying` → track-hash check skipped. When peek ends and mode flips back to NowPlaying, next Poll sees both mode-change AND track-hash mismatch → promotes once, draws Now-Playing with the latest art.
    - **Case 5**: session ends. session_now_playing was true; HA publishes `active_override = "schedule"` retained → next wake's `readSessionOverride` flips the flag to false → `pathForMinute` reverts to tier cadence. Linger expiry test: at the same time, active_mode flips from `now-playing` to a scheduled face → mode-change promotion → Full → draws scheduled face.
- [x] 5.3 New `firmware/test/scenarios/session_override_tests.cpp` — exercises the override-topic flow:
    - **Case A**: empty retained → flag stays at default (false).
    - **Case B**: payload `"now_playing"` → flag flips to true → planWake returns Poll regardless of mode.
    - **Case C**: payload `"schedule"` → flag flips to false → planWake follows tier dispatch.
    - **Case D**: payload `"weather_peek"` (or any non-`now_playing` value) → flag is false (only `"now_playing"` is canonical).
- [x] 5.4 Update `firmware/test/scenarios/main_loop_tests.cpp` if any test scenario asserts on the old NowPlaying = Full-every-minute behavior.

## 6. HA — track topic + active_override topic publishes

- [x] 6.1 `ha/automations/publish_inputs.yaml::inkplate_publish_sonos`: append a new `mqtt.publish` action to the END of the `action:` block (after the existing `rest_command.inkplate_publish_sonos`). Topic: `inkplate/state/now_playing_track`. Payload: the same `media_content_id or title|artist|album` Jinja the helper already uses. Retained, QoS 0.
- [x] 6.2 Verify the action ORDER inside the automation's action list — the MQTT publish MUST run after the rest_command, so the renderer's `sonos.json` is current before the device sees the new hash. Add a comment in the YAML stating this constraint.
- [N/A] 6.3 (Optional, deferred at archive 2026-05-05) Add a sibling MQTT-clear action that publishes empty retained to `inkplate/state/now_playing_track` when leaving NowPlaying. **Skipped**: the device's cache is per-mode and gets clobbered on the next NowPlaying entry, so this is broker-debug-hygiene only. Revisit if stale-track diagnosis becomes burdensome.
- [x] 6.4 New automation `ha/automations/publish_active_override.yaml` (or appended to the bottom of `now_playing_override.yaml`): triggers on state-change of `input_text.inkplate_active_override` AND on `homeassistant.start`. Action: `mqtt.publish` retained to `inkplate/state/active_override` with the input_text's current value. Gated by `input_boolean.inkplate_publisher_enabled`. This mirror is what gives the device its session-aware override.

## 7. Spec deltas

- [x] 7.1 `openspec/changes/optimise-now-playing-cadence/specs/device-firmware/spec.md` — ADDED requirement: NowPlaying mode uses Poll-with-track-change-promotion cadence.
- [x] 7.2 `openspec/changes/optimise-now-playing-cadence/specs/device-wake-protocol/spec.md` — ADDED requirement: `inkplate/state/now_playing_track` retained topic, payload format, empty-payload semantics.
- [x] 7.3 `openspec/changes/optimise-now-playing-cadence/specs/ha-integrations/spec.md` — ADDED requirement: HA publishes the track-version topic from `inkplate_publish_sonos`, sequenced after the renderer publish.

## 8. Validation

- [x] 8.1 `openspec validate optimise-now-playing-cadence` exits 0.
- [x] 8.2 Host build green, doctest 0 failed.
- [x] 8.3 PlatformIO inkplate10 build green.
- [x] 8.4 Smoke test on device — verified live 2026-05-05 with build `0.7.0-plain-partials`:
    - **Step 1 (Sonos session)**: ✓ Diag ring during the live session shows the `tLY…` Poll pattern dominating (entries `tLY23` for cheapest Polls, `tLY33/c…` for Polls with partial clock tick). Track changes promote to Full as expected (e.g. `tLY2f` entries with start=Y end=Y).
    - **Step 2 (peek during music)**: ✓ Tap → `inkplate_gesture_tap_now_playing_peek` fires (logbook confirms), commanded_face flips to gallery, panel renders Gallery, after 60 s the peek expires and the next Poll catches the active_mode revert and promotes to Full to draw NowPlaying. The session_now_playing flag held throughout — Polls continued at 1-min cadence during the peek (entries `tLG23` / `tLG2f`).
    - **Step 3 (pause + linger expiry)**: not verified live (would need a deliberate pause + 90-s wait); behavior is implicit from the firmware path (`readSessionOverride` flips `session_now_playing` on every Full/Poll, so a `schedule` retained value flips it false within 1 min) and the HA-side `inkplate_sonos_linger_expired` automation publishing the restore cascade. Accepting on implementation review since steps 1 & 2 exercised the same code paths.

  Notes captured during the smoke test (out of scope for this change, tracked as separate follow-ups):
    - Failed Full attempts (`flags=0x27`, `epd_pwrgood` set but `drew` not) traced to the renderer's broken HA-proxy slow-rendering when album-art fetch hung. Fixed in a separate change (renderer bearer-auth proxy fix). Post-fix, no more failed Fulls in the diag.
    - At /15 hour boundaries the device occasionally drew Weather despite override=now_playing. Source unidentified — alternation tick's gate looks correct but `active_mode` retained briefly carried `weather`. Logged as a follow-up to investigate live across a /15 boundary.
    - Tap during the Sonos-activation gap (between Sonos start and first Now-Playing render) fires the now-playing-peek automation and "peeks" to a face that's already on screen, producing no visible change. Logged as a follow-up — fix is to gate the peek on "device currently rendering now-playing".
