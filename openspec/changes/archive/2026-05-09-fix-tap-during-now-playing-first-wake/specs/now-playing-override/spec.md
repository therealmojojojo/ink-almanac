# now-playing-override Specification — delta

## ADDED Requirements

### Requirement: Tap interaction during now-playing

While `inkplate_active_override == now_playing`, taps on the device SHALL be interpreted by HA against `sensor.inkplate_commanded_face` (the truthful mirror of the face the device most recently drew, sourced from `inkplate/state/device.active_mode`):

1. **First-wake tap.** WHEN the mirror is anything other than `now-playing` (the screen is showing a stale schedule face from before the session started, a previous peek's target, or `unavailable` on cold boot), HA SHALL publish `inkplate/command/gesture_response = now-playing` (non-retained) and SHALL NOT publish to `inkplate/command/active_mode` (which already retains `now-playing` from the Sonos-started automation). The firmware's IMU grace window picks up the response and draws now-playing.

2. **Peek tap.** WHEN the mirror is `now-playing` (the screen is already showing now-playing), HA SHALL publish `inkplate/command/gesture_response = weather` and `inkplate/command/active_mode = weather` retained, hold for 60 seconds, then publish `active_mode = now-playing` retained and a wake pulse. The peek window is `mode: restart` so a tap during the window resets the 60-second clock — but in practice such a tap will be handled by the first-wake branch (mirror is no longer `now-playing` once the peek draw lands), which immediately returns the device to now-playing.

3. **Suppression.** Both branches SHALL respect the operator's quiet-hours window (`input_datetime.inkplate_quiet_start` to `inkplate_quiet_end`) and the schedule's Night-tier window (22:00 to 06:30). Within those windows, neither handler fires; the firmware's grace window times out and falls back to the retained `active_mode`.

The mirror sensor is the load-bearing piece of state. If the mirror disagrees with reality (device drew something but state-publish failed), the discriminator picks the wrong branch — but the behaviour degrades gracefully: a misclassified first-wake redraws now-playing (correct as long as the operator actually wants now-playing), and a misclassified peek redraws weather (one extra refresh).

#### Scenario: First-wake tap after music starts

- **WHEN** `media_player.kitchen_sonos` transitioned to `playing` 5 minutes ago, the device went to sleep before the wake pulse landed and is still on the previous tier's face (e.g. `weather`), and the operator double-taps the device
- **THEN** within 2 seconds HA publishes `inkplate/command/gesture_response = now-playing` (non-retained), the firmware's IMU grace window receives it, and the device draws the now-playing face. The retained `active_mode` topic remains `now-playing` (set by the Sonos-started automation); HA does not re-publish it.

#### Scenario: Subsequent tap peeks to weather

- **WHEN** music is playing, the device has previously drawn `now-playing` (`sensor.inkplate_commanded_face == 'now-playing'`), and the operator taps
- **THEN** HA publishes `gesture_response = weather` (non-retained) and `active_mode = weather` retained plus a wake pulse; the device draws weather. After 60 seconds, if the override is still `now_playing`, HA publishes `active_mode = now-playing` retained and a wake pulse so the device's next wake (timer or subsequent tap) returns to now-playing.

#### Scenario: Tap during a weather peek returns to now-playing

- **WHEN** the device is mid-peek showing weather (mirror = `weather`) and the operator taps
- **THEN** the first-wake branch fires (mirror != `now-playing`); HA publishes `gesture_response = now-playing`; the device draws now-playing. The peek's residual 60-second timer is allowed to elapse and publishes `active_mode = now-playing` retained — already the retained value, so it is a no-op.

#### Scenario: Tap during quiet hours suppresses both branches

- **WHEN** it is 02:30 and music is playing (override is still `now_playing` per the linger rule, since playback predates the quiet-hours window) and the operator taps
- **THEN** both the first-wake and peek conditions fail their quiet-hours guard, neither automation publishes, the firmware's IMU grace window times out at 2 seconds, and the firmware falls back to reading retained `active_mode = now-playing` and draws now-playing.
