# device-firmware Specification — delta

## MODIFIED Requirements

### Requirement: Tap detection

The device SHALL handle IMU-driven gestures (single and double taps from the LSM6DSO) as wake events that prompt HA to consult its mode-selection state machine and respond on a dedicated event channel.

On an `IMU` wake whose `TAP_SRC` register indicates a confirmed tap, the firmware SHALL:

1. Identify the tap kind (single / double) by reading the LSM6DSO's `TAP_SRC` register.
2. Apply the gyroscope door-filter to suppress false positives from fridge-door rotations.
3. Immediately partial-refresh the `ack` status glyph to acknowledge the tap (see "Status glyphs").
4. Publish the gesture to `inkplate/state/gesture` with `{ "kind": "single" | "double" }`.
5. Subscribe to the event channel `inkplate/command/gesture_response` for a short grace window (default 2 seconds).
6. If a payload arrives in-window, parse it as a face name and use it as the active mode for this wake.
7. If the wait times out, fall back to reading the retained `inkplate/command/active_mode` topic — the same path non-IMU branches use — and use that value as the active mode.

The firmware SHALL NOT interpret tap kinds as semantic actions (it does NOT "activate Weather peek" or "toggle Summary/Gallery"). Those decisions live in HA's override state machine (see `ha-integrations` override-precedence and the gesture-driven branches in HA's face-selection state machine). HA receives the gesture, consults its full state (Sonos, override precedence, quiet hours, schedule), decides what the new active mode should be, and publishes its decision on two topics: the non-retained event channel `inkplate/command/gesture_response` (consumed by the in-flight IMU wake's grace window) and the retained state channel `inkplate/command/active_mode` (consumed by all subsequent Full and Poll wakes until the schedule alternation overrides).

The grace-window listener uses the dedicated `gesture_response` topic — rather than `active_mode` directly — to avoid a race where the broker replays the previously retained `active_mode` on subscribe (which encodes the *current* mode, not HA's response to the just-fired tap) and the wait short-circuits on it before HA's fresh push arrives. By contract `gesture_response` is non-retained, so subscribe-time replay yields nothing and the wait truly waits for HA's push.

The timeout fallback to `resolveActiveMode` (which reads the retained `active_mode`) is a deliberate design choice. It preserves a useful side-effect of the device's older (racy) behavior: if a /15 alternation tick updated `active_mode` while the device was sleeping, a tap before the next Full still picks up that update — even when HA's gesture handler bails on a condition (e.g., quiet hours) and publishes nothing on `gesture_response`. The cost is one extra retained read (~50 ms on LAN); the benefit is bounded staleness on tap-during-suppressed-window scenarios.

This yields the following user-visible timing (assuming the INT1 wire from `add-device-firmware §5.4` is in place):

- ~1 s: `ack` glyph visible
- ~3–5 s: post-publish grace window closes; device renders either the gesture_response face (if HA responded) or the retained active_mode face (if HA bailed and was last updated by alternation or another tick)
- ~5–10 s: full-refresh completes, showing the face the device chose

If HA fails to process the gesture in the grace window (rare: HA restart, MQTT delay) AND the retained `active_mode` hasn't been updated since the last Full draw, the tap is effectively lost for the current wake; the face the device draws is the pre-gesture one. The user sees the ack glyph but no subsequent face change — which is honest UX (we heard you, but nothing changed) and aligns with the rest of the system's "HA owns policy" stance.

#### Scenario: Single tap during Summary hours

- **WHEN** a single tap occurs at 09:00 and HA's state machine decides to activate Weather peek
- **THEN** the device (a) partial-refreshes the ack glyph, (b) publishes `{ "kind": "single" }` to `state/gesture`, (c) waits up to 2 s on `command/gesture_response`, (d) receives `gesture_response = weather` from HA within ~150 ms, (e) fetches `/display/weather.png` and full-refreshes

#### Scenario: Single tap during quiet hours (HA suppresses)

- **WHEN** a single tap occurs at 02:30 and HA's state machine suppresses the gesture (quiet-hours condition fails on every gesture-handling automation)
- **THEN** the device (a) shows the ack glyph, (b) publishes the gesture, (c) waits up to 2 s during which HA publishes nothing on `command/gesture_response`, (d) the wait times out, (e) the device reads retained `active_mode = night` (unchanged) and renders Night — the user sees ack without a mode change

#### Scenario: Double tap during Gallery hours

- **WHEN** a double tap occurs during Gallery hours and HA's state machine toggles to Summary
- **THEN** the device publishes `{ "kind": "double" }`, receives `gesture_response = summary` within the grace window, fetches `/display/summary.png`, and full-refreshes

#### Scenario: Tap during a sleep-window alternation update

- **WHEN** the device is rendering Summary at 08:14 (parity slot 2 in the morning tier); HA's /15 alternation tick at 08:30 publishes `active_mode = weather` retained while the device is in deep sleep; the operator taps at 08:31; HA's gesture handler treats the tap as a flip-from-the-commanded-face and publishes `gesture_response = summary` (flipping the just-published Weather back to the tier main)
- **THEN** the device's IMU wake reads `gesture_response = summary` within the grace window, renders Summary, and publishes `state/device` with `active_mode = summary`. The retained `command/active_mode` ends up at "summary" (HA also publishes it as part of the flip), keeping subsequent Full wakes consistent until the next alternation tick

#### Scenario: Tap during a sleep-window alternation update with HA suppressed

- **WHEN** same setup as above but HA's gesture handler is suppressed (e.g., the operator taps at 02:30 during quiet hours, but a sleep-window alternation tick still ran)
- **THEN** the device's IMU wake times out on `gesture_response`, falls back to `resolveActiveMode`, reads retained `active_mode = weather` (the post-alternation value), and renders Weather — the tap is suppressed but the alternation update isn't lost

#### Scenario: Tap during a fast-path or full-cycle wake

- **WHEN** a tap fires while the device is already awake in the middle of a non-IMU wake
- **THEN** the LSM6DSO latches the tap in `TAP_SRC`; before sleeping, the firmware drains `TAP_SRC`, upgrades the wake semantically to IMU, shows the ack glyph, publishes the gesture, and waits on `gesture_response` — the tap is not lost
