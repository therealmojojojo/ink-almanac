# Fix the IMU gesture grace-window race

> **Status — 2026-05-05**: implementation done in working tree (firmware + HA + tests + architecture docs). This change captures the rationale and the spec deltas. Awaiting review and deployment.

## Why

Tap-to-face-change is broken in steady state. Diagnosed live from the operator's running device on 2026-05-05 ~08:07 EEST: a double-tap was detected, the gesture reached HA, HA's `gesture_override` automation flipped the commanded face from Summary to Weather and published it to `inkplate/command/active_mode` within the same broker tick, *and* the device still drew Summary on the IMU wake.

Root cause is in the firmware grace-window read. After publishing the gesture, the IMU branch in `firmware/src/main_loop.cpp` calls `mqttWaitForMessage(kTopicActiveMode, 2000ms)`. `active_mode` is retained — and the broker, by MQTT 3.1.1 contract, replays the retained value to any new subscriber immediately on subscribe. The wait's "exit on first captured message" loop in `firmware/src/hal/real/RealTransport.h::waitImpl` then short-circuits within ~50 ms on the *previously retained* value (the device's current mode), unsubscribes, and proceeds. HA's freshly published flip arrives a few hundred ms later but the device has already moved on. The tap appears ignored.

The race is permanent: it fires on every IMU wake whose desired flip is encoded in `active_mode`, because `active_mode` is *always* retained and *always* set to the device's currently-drawn face. The bug only doesn't trigger when `active_mode` happens to be empty (cold boot before any HA publish, broker restart). That's why initial bring-up tests passed.

The same race affects the now-playing peek path in `gesture_override.yaml`, although less visibly — a tap during music momentarily flipping to Summary or Gallery is also non-deterministic on the in-flight wake.

## What Changes

The fix is to separate the state channel (retained `active_mode`) from the event channel (a fresh per-tap response). Three pieces:

### A. New non-retained MQTT topic — `inkplate/command/gesture_response`

Plain string, same value-space as `active_mode` (face name). Published by HA's gesture automations as part of their action block, alongside the existing retained `active_mode` and `wake` publishes. Non-retained by contract — the broker has nothing to replay on subscribe, so the firmware's wait truly waits for HA's push and isn't fooled by stale state.

Empty payload is not a meaningful state for this topic (HA either fires the automation and publishes a face, or doesn't fire and publishes nothing). The firmware treats absence-of-message as "HA bailed; fall back".

### B. Firmware

- `firmware/include/config.h`: add `kTopicGestureResponse = "inkplate/command/gesture_response"`.
- `firmware/src/main_loop.cpp` IMU branch: change `mqttWaitForMessage` target from `kTopicActiveMode` to `kTopicGestureResponse`.
- On timeout (HA bailed on a condition or didn't respond within 2 s), the IMU branch SHALL fall back to `resolveActiveMode(transport, hour)` — exactly the same retained read non-IMU branches do. This preserves the side-effect benefit the original racy code accidentally provided: if a /15 alternation tick updated `active_mode` while the device was sleeping, a tap before the next Full still picks up the new face.
- `firmware/src/hal/real/RealTransport.h::mqttWaitForMessage`: doc comment updated to spell out the "non-retained event topic only" contract.

### C. HA

`ha/automations/gesture_override.yaml` — both gesture-handling automations (schedule-tap phase flip, now-playing-peek) gain one extra `mqtt.publish` to `inkplate/command/gesture_response` with `retain: false`, placed before the existing `active_mode` publish. The `gesture_response` carries the same face value as `active_mode` (the flipped or peek face). The retained `active_mode` continues to drive subsequent Full and Poll wakes.

### D. Test harness

`firmware/test/hal/mock/MockTransport`: track non-retained pushes per topic in a `pending_push_` map; `mqttWaitForMessage` returns the retained value if present, else drains `pending_push_`. This models the broker's "deliver retained on subscribe, otherwise wait for push" behavior so the publish hook can simulate HA's gesture_response without having to use a retained topic.

`firmware/test/scenarios/main_loop_tests.cpp`: three IMU test cases updated. Hooks now publish `gesture_response` (non-retained) alongside `active_mode` (retained); the quiet-hours test models HA correctly bailing on its condition by installing an empty hook (no `gesture_response` push → device times out and falls back).

## Capabilities

### Modified Capabilities

- `device-firmware` — Tap detection: requirement now subscribes to `gesture_response` for the grace window, with `active_mode` re-read as the timeout fallback.

### New Capabilities

None. The new MQTT topic is part of an existing capability pair (firmware tap detection + HA gesture handling). The canonical `ha-integrations` spec doesn't currently carry a gesture-handler requirement, so the HA-side publishing contract is captured implicitly in the device-firmware requirement's narrative ("HA publishes on two topics: ..."). Adding a new ha-integrations requirement here would expand scope; it can come later in a dedicated change if/when the gesture-handler contract needs first-class spec coverage.

## Impact

- **One-line battery hit**: on IMU wakes where HA *does* respond (the common case), the wait now short-circuits on first push exactly like before. On IMU wakes where HA bails (quiet hours, gesture handler condition rejected), the wait runs to its 2 s deadline and adds one extra `mqttReadRetained` (~50 ms broker round-trip on LAN). Negligible.
- **Protocol compatibility**: deploying HA before firmware is safe (HA publishes to a topic no one subscribes to). Deploying firmware before HA also works, but every tap times out until HA is updated. Recommended: deploy HA first via `ha/deploy.sh`, then OTA the firmware.
- **No conflict with `optimise-now-playing-cadence`** (in flight, 27/29 tasks): adjacent files but non-overlapping changes. Both can land independently. This fix actually closes a latent bug in that change's now-playing-peek path that wasn't called out in its design.md.
- **No conflict with `add-pushable-wake-schedule`** (mid-archive): different code paths.
- **No conflict with `add-night-text-clock-partials`** (just opened): different surface.
- **Useful prior to `research-single-tap-detection`** completing: any future "real single-tap distinct from double-tap" semantics depend on the grace window actually working.

## Risks

1. **HA forgets to publish `gesture_response`** for a future new gesture path. Mitigation: the firmware's timeout fallback to `resolveActiveMode` means a missing `gesture_response` degrades gracefully — the wake still draws *some* face (the persisted current_mode, or a sleep-window-updated `active_mode`), just not the freshest one. No crash, no infinite wait, no lost tap (the gesture is still visible to HA on `state/gesture`).
2. **Two publishes per gesture on HA side**. If HA's MQTT add-on is overloaded, the two publishes could interleave with other traffic and miss the 2 s window. Same failure mode as today's `active_mode` publish missing the window — not a new failure class. The `gesture_response` publish is sub-second on a healthy HA; both publishes complete within tens of ms.
3. **Operator-typed manual publish to `command/active_mode`** during a tap window. Today such a publish would land in the in-flight wake's grace window via the retained replay (and the user would unintentionally drive the tap response). Under the new contract, manual publishes to `active_mode` are just state updates and don't influence the in-flight wake — only `gesture_response` does. This is the correct shape; flagged here so the operator dashboard reflects the new semantics if it ever exposed both topics.
