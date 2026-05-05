# ha-integrations Specification — delta

## ADDED Requirements

### Requirement: HA publishes the Now-Playing track-version topic

HA SHALL publish a retained MQTT message to `inkplate/state/now_playing_track` whenever the Sonos media player's `media_content_id` (or its title/artist/album fallback) changes while playing. The publish SHALL be integrated into the existing `inkplate_publish_sonos` automation (`ha/automations/publish_inputs.yaml`) as the FINAL action in its `action:` block, after the existing `rest_command.inkplate_publish_sonos` (which updates the renderer's `sonos.json`).

Payload: identical Jinja expression to the existing `input_text.inkplate_now_playing_content_id` helper:

```jinja
{{ state_attr('media_player.kitchen_sonos','media_content_id')
   or (state_attr('media_player.kitchen_sonos','media_title') ~ '|'
       ~ state_attr('media_player.kitchen_sonos','media_artist') ~ '|'
       ~ state_attr('media_player.kitchen_sonos','media_album_name')) }}
```

A YAML comment in the automation SHALL state the sequencing constraint ("MUST run after rest_command.inkplate_publish_sonos") so a future editor doesn't reorder the actions and reintroduce the renderer-vs-MQTT race.

#### Scenario: Sonos plays a new track → renderer + MQTT updated in order

- **WHEN** the operator presses play on a new track in Sonos
- **THEN** HA's `inkplate_publish_sonos` automation fires: first the `rest_command.inkplate_publish_sonos` POSTs the new track metadata to the renderer (`sonos.json` updated synchronously); then the `mqtt.publish` step writes the new track identifier to `inkplate/state/now_playing_track` retained. The device, on its next Poll wake, sees the new hash and fetches an image rendered against the up-to-date `sonos.json`

#### Scenario: HA start re-publishes both the renderer input and the track topic

- **WHEN** Home Assistant boots while Sonos is currently playing
- **THEN** the `inkplate_publish_sonos` automation fires on `homeassistant.start` (existing trigger), republishing both the renderer's `sonos.json` AND the retained MQTT track-version topic. The device's next NowPlaying Poll sees the (re-published) retained value and continues to dedupe correctly

#### Scenario: Volume / seek changes do NOT re-publish

- **WHEN** the operator adjusts Sonos volume or seeks within the current track (`media_content_id` unchanged)
- **THEN** `inkplate_publish_sonos`'s existing trigger does NOT fire (it triggers on state and media_content_id, not on every attribute), so neither the renderer publish nor the track-version MQTT publish runs. The device's NowPlaying Polls continue to find the same hash and stay quiet

### Requirement: HA mirrors `inkplate_active_override` to MQTT

HA SHALL run an automation (`ha/automations/publish_active_override.yaml` or appended to an existing automation file) that mirrors the value of `input_text.inkplate_active_override` to retained MQTT topic `inkplate/state/active_override`. The automation SHALL trigger on:

- State-change of `input_text.inkplate_active_override` (any value transition).
- `homeassistant.start` (re-publish after HA / broker restart).

Action: `mqtt.publish` with `topic: inkplate/state/active_override`, `payload: "{{ states('input_text.inkplate_active_override') }}"`, `retain: true`, `qos: 0`. Gated by `input_boolean.inkplate_publisher_enabled` per the existing publisher convention.

This mirror is what gives the device its session-aware cadence override — the device polls every minute while a Sonos session is active even when a peek has flipped active_mode away from now-playing.

#### Scenario: Sonos starts → override mirror flips → device picks up the cadence change

- **WHEN** Sonos transitions to playing (outside quiet hours), HA's `inkplate_sonos_play_start` flips `input_text.inkplate_active_override` to `now_playing`
- **THEN** the override-mirror automation fires (state-change trigger), publishes `inkplate/state/active_override = now_playing` retained; the device's next Full/Poll/PollPartial wake reads it, flips `session_now_playing` to true, and from this point pathForMinute returns Poll for every minute until the session ends

#### Scenario: Linger expiry → override mirror flips back

- **WHEN** Sonos has been paused, the linger timer expires, and HA's `inkplate_sonos_linger_expired` runs the restore cascade and sets `input_text.inkplate_active_override` to `schedule`
- **THEN** the override-mirror automation fires, publishes `inkplate/state/active_override = schedule` retained; the device's next wake reads it, flips `session_now_playing` to false, and from this point pathForMinute follows the tier dispatch (Fulls + Partials only under the operator's no-daytime-Polls config)
