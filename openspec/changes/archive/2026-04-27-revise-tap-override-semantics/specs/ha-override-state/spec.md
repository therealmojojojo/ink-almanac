# Spec — ha-override-state

## Purpose

The HA override state machine decides which face the device shows at any moment. It receives four event classes (schedule boundaries, taps, Sonos state changes, HA lifecycle events), maintains four helpers (`active_override`, `prior_override`, `scheduled_face`, `weather_peek_expires_at`), and produces one authoritative output — the retained `inkplate/command/active_mode` MQTT topic. The device trusts only this retained value; everything else HA emits (the advisory `inkplate/command/wake` pulse, the per-face renderer-input POSTs) is latency / freshness plumbing.

## Requirement: State set and activation model

The capability SHALL expose the following `active_override` states:

| State | Activator | Lifetime |
|---|---|---|
| `schedule` | Default; ha-boot and deactivation fallthrough | No expiry |
| `weather_peek` | Single tap | `input_number.inkplate_weather_peek_seconds` (default 60) |
| `summary_gallery_toggle` | Double tap | Until next scheduled boundary |
| `now_playing` | Sonos entering `playing` state | Latched; ended by Sonos not-playing + `input_number.inkplate_linger_seconds` (default 90) |

Activation follows these rules:

- **Explicit beats ambient outside quiet hours.** A single tap SHALL activate `weather_peek` regardless of the current `active_override`, provided the current time is outside the quiet window defined by `input_datetime.inkplate_quiet_{start,end}`.
- **Double tap remains suppressed during `now_playing`.** A double tap with `active_override == now_playing` SHALL NOT change state (deliberate asymmetry; see scenario "Double tap during music is suppressed").
- **Quiet-hours suppression is policy, not priority.** During quiet hours, both tap automations and Sonos-start-playing activation SHALL be suppressed. Taps are acknowledged on-device via the `ack` glyph; HA records nothing.
- **Schedule boundaries always update `scheduled_face`.** Whether or not they publish a new `active_mode` depends on the current override.

### Scenario: Single tap during Now-Playing activates weather peek with correct prior

- **GIVEN** `active_override == now_playing` and music is playing
- **WHEN** the device publishes `{"kind":"single"}` on `inkplate/state/gesture` outside quiet hours
- **THEN** HA SHALL set `active_override = weather_peek`, `prior_override = now_playing`, arm `weather_peek_expires_at = now + 60 s`, publish retained `inkplate/command/active_mode = weather`, and pulse `inkplate/command/wake`

### Scenario: Double tap during Now-Playing is suppressed

- **GIVEN** `active_override == now_playing` and music is playing
- **WHEN** the device publishes `{"kind":"double"}` on `inkplate/state/gesture` outside quiet hours
- **THEN** HA SHALL NOT change `active_override`, `prior_override`, or retained `active_mode`

### Scenario: Tap during quiet hours is suppressed

- **GIVEN** the current time is within `inkplate_quiet_{start,end}`
- **WHEN** the device publishes any gesture on `inkplate/state/gesture`
- **THEN** HA SHALL NOT change `active_override` or retained `active_mode`

## Requirement: `prior_override != active_override` invariant

HA SHALL preserve `prior_override != active_override` at all times. Re-triggering the currently-active state (single tap while `active_override == weather_peek`, or double tap while `active_override == summary_gallery_toggle`) SHALL refresh the state's lifetime (peek expiry, toggled face) but SHALL NOT overwrite `prior_override`.

### Scenario: Second single tap during peek extends without losing prior

- **GIVEN** `active_override == weather_peek` and `prior_override == schedule`
- **WHEN** the device publishes `{"kind":"single"}` during the peek
- **THEN** HA SHALL rearm `weather_peek_expires_at = now + peek_seconds`, republish retained `active_mode = weather`, and leave `prior_override == schedule`

### Scenario: Re-toggle during summary_gallery_toggle preserves prior

- **GIVEN** `active_override == summary_gallery_toggle` and `prior_override == schedule`
- **WHEN** the device publishes `{"kind":"double"}` during the toggle
- **THEN** HA SHALL flip the published `active_mode` between `summary` and `gallery` (whichever is not currently published) and leave `prior_override == schedule`

## Requirement: Unified restore cascade

Every deactivation site SHALL resolve the restored state via the same cascade, in order:

1. If `prior_override == now_playing` AND `media_player.kitchen_sonos.state == playing` → restore `now_playing` (publish `active_mode = now-playing`)
2. Else if `prior_override == weather_peek` AND `weather_peek_expires_at > now` → restore `weather_peek` (publish `active_mode = weather`)
3. Else if `prior_override == summary_gallery_toggle` → restore `summary_gallery_toggle` (publish `active_mode = scheduled_face`)
4. Else → restore `schedule` (publish `active_mode = scheduled_face`)

The cascade is reused by:

- `inkplate_weather_peek_expiry` (triggered at `weather_peek_expires_at`)
- `inkplate_sonos_linger_expired` (triggered when the 90 s linger timer fires with Sonos not playing)
- `inkplate_ha_start_stale_peek_cleanup` (triggered at HA start if `active_override == weather_peek` AND `weather_peek_expires_at < now`)

After each restore the cascade SHALL reset `prior_override = schedule`. The cascade consumes the prior; leaving it in place would make the next activation save an already-used prior and, in the `prior == active` case (e.g., peek-with-music-still-playing), violate the invariant.

### Scenario: Peek expiry with music still playing returns to Now-Playing

- **GIVEN** `active_override == weather_peek`, `prior_override == now_playing`, music is playing, `weather_peek_expires_at` has just been reached
- **WHEN** the peek-expiry automation fires
- **THEN** HA SHALL set `active_override = now_playing` and publish retained `active_mode = now-playing`

### Scenario: Peek expiry with music paused falls to schedule

- **GIVEN** `active_override == weather_peek`, `prior_override == now_playing`, Sonos is paused or idle, `weather_peek_expires_at` has just been reached
- **WHEN** the peek-expiry automation fires
- **THEN** HA SHALL set `active_override = schedule` and publish retained `active_mode = <scheduled_face>`

### Scenario: Linger fire-event during active peek is a no-op

- **GIVEN** `active_override == weather_peek` (a tap preempted Now-Playing during the linger window), `prior_override == now_playing`
- **WHEN** `timer.inkplate_now_playing_linger` fires and Sonos is not playing
- **THEN** HA SHALL NOT change `active_override`, `prior_override`, or retained `active_mode`

### Scenario: HA start with expired stuck peek self-heals

- **GIVEN** HA just started, `active_override == weather_peek`, and `weather_peek_expires_at < now()`
- **WHEN** the `homeassistant` `start` event fires
- **THEN** HA SHALL run the unified restore cascade and publish the resulting retained `active_mode`

## Requirement: Advisory wake pulse

HA SHALL publish a non-retained `inkplate/command/wake` pulse on every activation and deactivation that changes `active_override` or the retained `active_mode`. The pulse is advisory — the device's correctness depends only on the retained `active_mode`. A missed pulse delays visibility to the device's next natural wake (≤ one timer period, typically 60 s) but does not produce an incorrect face.

### Scenario: Device missed the wake pulse sees correct face on next wake

- **GIVEN** HA published a new retained `active_mode` and the device's MQTT subscription missed the non-retained `wake` pulse (e.g., device was mid-deep-sleep)
- **WHEN** the device's next timer wake fires
- **THEN** the device SHALL read the retained `active_mode` and display the correct face
