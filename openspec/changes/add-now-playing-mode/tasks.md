## 1. HA helper entities

- [x] 1.1 Create an input_text helper for the active-override state holder (values: `schedule`, `now_playing`, `weather_peek`, `summary_gallery_toggle`)
- [x] 1.2 Create an input_text helper for the prior-override state (saved when Now-Playing activates)
- [x] 1.3 Create a timer helper for the linger countdown (duration configurable from input_number)
- [x] 1.4 Create input_number helpers for `linger_seconds`, `quiet_hours_start`, `quiet_hours_end`
- [x] 1.5 Create an input_text helper for `kitchen_sonos_entity` (default `media_player.kitchen_sonos`)

## 2. Activation automation

- [x] 2.1 Trigger: configured Sonos entity transitions to `playing`
- [x] 2.2 Guard: not within quiet-hours window
- [x] 2.3 Action: save prior override state, set active state to `now_playing`, call the album-art prefetch action, wait for renderer confirmation, issue device-wake signal

## 3. Track-change detection

- [x] 3.1 Trigger: `media_content_id` (or fallback tuple) changes while state is `playing`
- [x] 3.2 Action: re-run album-art prefetch, re-render Now-Playing PNG, issue device-wake signal
- [x] 3.3 Ignore: volume, seek, and other non-track attribute changes

## 4. Deactivation and linger

- [x] 4.1 Trigger: Sonos transitions away from `playing` (to `paused` or `idle`)
- [x] 4.2 Start linger timer with `linger_seconds`
- [x] 4.3 If Sonos returns to `playing` before the timer fires, cancel the linger
- [x] 4.4 On timer fire: restore prior override if still valid, else fall back to schedule; issue device-wake signal to pick up the new face

## 5. Album-art prefetch

- [x] 5.1 Define staging path (e.g., `~/inkplate-cache/now-playing/current.jpg` on the Mac host)
- [x] 5.2 Implement the fetch (HA `shell_command` or a renderer endpoint that reads the entity_picture URL server-side)
- [x] 5.3 On 404 / timeout, leave the staging path absent so the renderer uses the placeholder treatment
- [x] 5.4 Clean up stale staged art periodically (older than 24h)

## 6. Source mapping

- [x] 6.1 Create a YAML mapping file in HA config for source → indicator label
- [x] 6.2 Populate with Spotify, Apple Music, TuneIn, AirPlay, default `SONOS`
- [x] 6.3 Inject source-indicator value into the renderer call

## 7. Precedence enforcement

- [x] 7.1 When single-tap Weather peek or double-tap toggle fires, suppress if active override is `now_playing`
- [x] 7.2 When Now-Playing deactivates, restore prior override only if still valid (time-window still open)
- [ ] 7.3 Verify scenario: Weather peek followed by music → Weather peek not restored if 5-minute window expired
- [ ] 7.4 Verify scenario: double-tap toggle followed by music → toggle restored if not past next schedule boundary

## 8. Quiet-hours suppression

- [x] 8.1 Implement the time-window check in the activation automation
- [x] 8.2 Implement a boundary re-evaluation: when the window ends while music is still playing, evaluate activation
- [ ] 8.3 Verify scenario: music at 04:58 continues past 05:00 → Now-Playing activates at 05:00

## 9. Device-wake signaling

- [x] 9.1 Define the mechanism (MQTT vs HTTP) — coordinate with `add-device-firmware`
- [x] 9.2 Implement the wake call from HA
- [ ] 9.3 Verify device latency within the 10-second target for activation and track-change

## 10. Integration and review

- [ ] 10.1 End-to-end test: play a Spotify playlist on the kitchen Sonos, observe Now-Playing activates within 10 seconds with correct album art and source indicator
- [ ] 10.2 End-to-end test: skip to next track; observe re-render within 10 seconds
- [ ] 10.3 End-to-end test: stop playback; observe frame reverts to schedule after 90s linger
- [ ] 10.4 End-to-end test: play at 02:30 during quiet hours; observe Night mode stays active
- [ ] 10.5 Verify every spec scenario passes
