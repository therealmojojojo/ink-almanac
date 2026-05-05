# device-wake-protocol Specification — delta

## ADDED Requirements

### Requirement: NowPlaying track-version MQTT topic

HA SHALL publish the device's current Now-Playing track identifier to the retained MQTT topic `inkplate/state/now_playing_track`. The payload SHALL be a plain string (NOT JSON), formed from the Sonos track attributes:

- Primary: `media_content_id` (Spotify URI, AirPlay GUID, etc.) when present and non-empty.
- Fallback: `media_title|media_artist|media_album_name` joined by `|` when `media_content_id` is empty.

This is the same expression HA already computes for `input_text.inkplate_now_playing_content_id` (helper in `ha/integrations/helpers.yaml`).

The topic SHALL be retained so a device that wakes between track changes immediately sees the current track on subscribe — no timing coordination with HA is needed.

The empty-string payload SHALL be a valid value meaning "no track signal" (Sonos has never played, or playback ended and HA cleared the topic). The device's Poll handler treats it as a no-op.

#### Scenario: Track change is reflected in the retained topic

- **WHEN** Sonos transitions from playing track A to playing track B
- **THEN** within the latency of HA's Sonos integration (≤ 1 s typical), the broker's retained value at `inkplate/state/now_playing_track` is track B's identifier; track A's identifier is overwritten

#### Scenario: Empty payload after pause + linger expiry

- **WHEN** Sonos pauses, the linger timer expires, and HA restores the prior override (e.g., back to the schedule)
- **THEN** the retained `inkplate/state/now_playing_track` MAY be left at the last-played track's identifier OR cleared to empty; either is acceptable. The device's Poll has already left NowPlaying mode by this point (mode-change-promotion to the schedule face), so the track topic is irrelevant until the next NowPlaying entry

### Requirement: Track-version publish is sequenced after the renderer publish

HA's `inkplate_publish_sonos` automation SHALL publish the track-version topic AFTER updating the renderer's `sonos.json` (the existing `rest_command.inkplate_publish_sonos` step). The track-version `mqtt.publish` SHALL be the FINAL action in the automation's `action:` block.

The sequencing requirement is structural: HA actions within a single automation run sequentially, so placing the MQTT publish after the REST call guarantees the renderer's `/display/now-playing.png` is current with the new track BEFORE the device can see the new hash and decide to fetch a fresh image. A separate, parallel automation publishing the track topic would race the renderer publish and risk the device fetching a stale image.

#### Scenario: Track change → renderer ready → device fetches fresh image

- **WHEN** Sonos transitions to a new track at T=0
- **THEN** at T≈0.1 s HA's `inkplate_publish_sonos` POSTs the new track to the renderer (`sonos.json` updated, the next `/display/now-playing.png` request will reflect track B); at T≈0.2 s HA publishes the track-version topic to MQTT retained; at T≤60 s the device's next Poll wakes, reads the new hash, promotes to Full, fetches `/display/now-playing.png` and gets an image rendered against the up-to-date `sonos.json`

#### Scenario: A separate track-publish automation would race — and is forbidden

- **WHEN** an operator considers adding a sibling automation triggered on `media_content_id` change that publishes the track-version topic in parallel with `inkplate_publish_sonos`
- **THEN** this is rejected by the spec; the publish MUST live inside `inkplate_publish_sonos`'s sequential action list. Two parallel automations would race, and a device that wins the race fetches an image rendered from the *old* `sonos.json` while caching the *new* track-version hash, leaving the panel permanently stale until the next track change

### Requirement: Active-override MQTT topic

HA SHALL publish the device-relevant view of the override state machine to retained MQTT topic `inkplate/state/active_override`. The payload SHALL be a plain string mirroring the value of `input_text.inkplate_active_override`:

- `"now_playing"` — Sonos session is active. Device runs per-minute Poll cadence regardless of the visible face.
- `"schedule"` — no override; device follows tier cadence.
- `"weather_peek"`, `"summary_gallery_toggle"` — non-Sonos overrides; device follows tier cadence (the visible face is governed by `inkplate/command/active_mode`; cadence is governed by tier).
- `""` (empty) — the device leaves its cached `session_now_playing` flag untouched (HA hasn't published yet, or has explicitly cleared the topic).

The device SHALL NOT enumerate values beyond the `now_playing` distinction — any non-empty value other than `"now_playing"` SHALL set the session flag to `false`. New override values introduced by HA later (e.g., a hypothetical `"hn_peek"`) SHALL be safely treated as "not now-playing" without firmware changes.

#### Scenario: Override topic is published on every input_text state change

- **WHEN** HA's override-state-machine flips `input_text.inkplate_active_override` (e.g., Sonos starts playing → `now_playing`; linger expires → `schedule`)
- **THEN** the publish_active_override automation fires, publishes the new value retained to `inkplate/state/active_override`; the device's next Full/Poll/PollPartial wake reads the new value and updates `wake::Persisted::session_now_playing` accordingly

#### Scenario: HA start re-publishes the override

- **WHEN** Home Assistant restarts (broker may also restart, losing retained state)
- **THEN** the publish_active_override automation re-fires on `homeassistant.start`, restoring the retained value from the input_text helper's persisted state; the device's next wake (within ≤30 min worst case at midday Full cadence under no-daytime-Polls tiers) picks up the restored value

#### Scenario: Override changes during a peek

- **WHEN** the device is in a tap-peek (active_mode = `summary`, session = `now_playing`), and an operator manually changes the input_text to `schedule` from the HA UI
- **THEN** the publish_active_override automation fires, publishes `schedule` retained; the device's next Poll (≤60 s, because session was true) reads the new value and flips the session flag to false; from that point the device follows tier cadence; the visible face follows whatever active_mode now points at (the operator likely paired the override change with an active_mode change too)
