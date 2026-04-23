## ADDED Requirements

### Requirement: Activation rule

When the kitchen Sonos media player transitions to state `playing`, the Now-Playing face SHALL become the active face, preempting any scheduled face or lower-precedence override.

#### Scenario: Music starts during Summary hours

- **WHEN** it is 08:15 (Summary hours), the schedule is showing Summary, and `media_player.kitchen_sonos` transitions from `idle` to `playing`
- **THEN** within 10 seconds the Now-Playing face is the active face, the renderer has produced `/display/now-playing.png` with the current track's data, and the device has been signaled to wake and fetch

#### Scenario: Music starts during Gallery hours

- **WHEN** it is 15:00 (Gallery hours) and Sonos starts playing
- **THEN** the Gallery face is preempted by Now-Playing without regard to Gallery's quiet-hours semantics

### Requirement: Linger rule

When playback ends (Sonos transitions to `paused` or `idle`), Now-Playing SHALL remain active for a configurable linger duration before the schedule or a prior override resumes. Default linger is 90 seconds.

During linger, if Sonos returns to `playing` (e.g., a between-track pause ending), the linger SHALL reset and Now-Playing continues without flicker.

#### Scenario: Brief inter-track pause

- **WHEN** Sonos transitions playing → paused → playing within 15 seconds
- **THEN** Now-Playing never reverts to the schedule; no re-render of a different face occurs

#### Scenario: Playback genuinely ends

- **WHEN** Sonos transitions to idle and remains idle for longer than the linger duration (90s)
- **THEN** the schedule (or prior valid override) resumes and the device is signaled to fetch the new active face's PNG

### Requirement: Track-change detection and re-render

The renderer SHALL re-render Now-Playing only when a track changes, not on every Sonos attribute update. Track change is detected by a stable attribute such as `media_content_id` (Sonos-specific) or by a combination of title + artist + album if the content-id attribute is unavailable.

On track change, the album-art binary SHALL be fetched to a local staging path, pre-processed, and the Now-Playing PNG re-rendered before the device is signaled to wake.

#### Scenario: Volume change does not trigger re-render

- **WHEN** the kitchen Sonos volume changes but the track does not
- **THEN** no re-render occurs and the device is not woken

#### Scenario: Track change triggers full refresh

- **WHEN** the kitchen Sonos advances to a new track
- **THEN** the new album art is fetched, the Now-Playing PNG is re-rendered, and the device is signaled to wake and fetch the new PNG

### Requirement: Album-art preparation

On track change, the album-art binary SHALL be fetched via the Sonos `entity_picture` URL to a local staging path on the Mac host. The renderer SHALL use this local path rather than fetching the URL at render time. If the fetch fails, the fallback album-art placeholder (specified by `dashboard-faces`) SHALL be used.

#### Scenario: Successful art fetch

- **WHEN** a track change occurs and the Sonos `entity_picture` URL returns a valid image
- **THEN** the image is saved to the staging path, is readable by the renderer, and appears (pre-dithered) in the rendered Now-Playing PNG

#### Scenario: Art fetch fails

- **WHEN** the Sonos `entity_picture` URL returns 404 or times out
- **THEN** Now-Playing still renders using the placeholder album-art treatment, track info displays correctly, and the failure is logged without halting the override

### Requirement: Device wake signal

When Now-Playing becomes the active face (either on activation or on track change), HA SHALL signal the Inkplate device to wake and fetch the new PNG, rather than waiting for the device's next scheduled check-in.

The wake signaling mechanism is defined by `add-device-firmware`; this specification only asserts that it is called.

#### Scenario: Wake after activation

- **WHEN** Now-Playing activates from an idle Sonos state
- **THEN** within 10 seconds of activation, HA has issued a wake signal to the device

#### Scenario: Wake after track change

- **WHEN** the current track changes during active Now-Playing
- **THEN** within 10 seconds of the change, HA has issued a wake signal to the device

### Requirement: Precedence among overrides

The precedence order from highest to lowest SHALL be:

1. Now-Playing (during active playback and linger)
2. Single-tap Weather peek (5-minute window)
3. Double-tap Summary/Gallery toggle (persists until next scheduled transition)
4. Scheduled face (Summary / Gallery / Night per the clock)

When Now-Playing activates over a lower-precedence override, it SHALL save the prior override state. When Now-Playing deactivates (after linger), the saved override SHALL be restored if still time-valid; otherwise the schedule governs.

#### Scenario: Music interrupts a Weather peek

- **WHEN** the operator single-taps at 14:00 to peek at Weather (5-minute override) and Sonos starts playing at 14:02
- **THEN** Now-Playing preempts Weather; when music stops at 14:06 and linger ends at 14:07:30, the Weather peek is no longer time-valid (past its 5-minute window) and the schedule (Gallery) resumes

#### Scenario: Music interrupts a double-tap toggle

- **WHEN** the operator double-taps to force Summary during Gallery hours, then music plays for 20 minutes, then stops
- **THEN** after the linger, the double-tap override is still persistent and the frame returns to Summary (not Gallery)

### Requirement: Quiet-hours suppression

Between configurable quiet-start and quiet-end times (defaults 00:00 and 05:00), Sonos playback SHALL NOT trigger Now-Playing. Night mode remains the active face during this window even if music plays.

#### Scenario: Late-night music plays briefly

- **WHEN** it is 02:30 and Sonos starts playing
- **THEN** Night mode remains the active face, no wake signal is issued for Now-Playing, and the renderer does not produce a Now-Playing PNG for this playback

#### Scenario: Music at the boundary

- **WHEN** music starts at 04:58, quiet-hours ends at 05:00, and the track is still playing at 05:01
- **THEN** Now-Playing activates at 05:00 when the quiet-hours window ends (HA re-evaluates activation on schedule boundaries or polls at reasonable cadence)

### Requirement: Source indicator

The source indicator shown on Now-Playing (e.g., `SONOS · SPOTIFY`) SHALL be populated from the Sonos `source` attribute or equivalent. Supported mappings at minimum:

- Spotify (via Sonos) → `SONOS · SPOTIFY`
- Apple Music (via Sonos) → `SONOS · APPLE MUSIC`
- TuneIn radio → `SONOS · RADIO`
- AirPlay → `SONOS · AIRPLAY`
- Unknown or unmapped sources → `SONOS`

#### Scenario: Spotify playback

- **WHEN** Sonos is playing a track sourced from Spotify
- **THEN** the source indicator shows `SONOS · SPOTIFY`

#### Scenario: Unknown source

- **WHEN** the Sonos source attribute returns a value not present in the mapping
- **THEN** the source indicator shows `SONOS` without a second segment

### Requirement: Configurable defaults

The following parameters SHALL be configurable via HA helpers or equivalent:

- `linger_seconds` (default 90)
- `quiet_hours_start` (default `00:00`)
- `quiet_hours_end` (default `05:00`)
- `kitchen_sonos_entity` (default `media_player.kitchen_sonos`)

Changes to these parameters SHALL take effect on the next Sonos state evaluation without requiring a restart.

#### Scenario: Changing the linger

- **WHEN** the operator updates `linger_seconds` from 90 to 30 via HA
- **THEN** subsequent playback-end events use the new 30-second linger, applied to any future transitions
