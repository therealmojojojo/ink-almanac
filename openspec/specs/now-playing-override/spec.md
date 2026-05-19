# now-playing-override Specification

## Purpose
TBD - created by archiving change add-now-playing-mode. Update Purpose after archive.
## Requirements
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

### Requirement: HA-start reconciliation

When Home Assistant starts, the now-playing activation rule SHALL be re-evaluated. State-change triggers do not fire for transitions HA was not observing — so any Sonos `→ playing` transition that occurred while HA was restarting (deploy, supervisor update, host reboot) is otherwise lost. Without reconciliation, the override remains on whatever value persisted across the restart, which can disagree with current Sonos state.

On `homeassistant.start`, if `media_player.kitchen_sonos == 'playing'` AND `input_text.inkplate_active_override != 'now_playing'` AND it is outside quiet hours, HA SHALL run the activation cascade: save the current `active_override` to `prior_override`, set `active_override = now_playing`, cancel any running linger timer, refresh `now_playing_content_id` from current Sonos media, publish `inkplate/command/active_mode = now-playing` retained, and publish a wake pulse to `inkplate/command/wake`.

If Sonos's integration is still reconnecting at `homeassistant.start` (state is `unavailable`), the condition guard fails and no action is taken; the subsequent `unavailable → playing` transition is handled by the existing `inkplate_sonos_play_start` activation path.

This Requirement does not introduce a new state transition. It closes a coverage gap in the existing activation rule by adding a third trigger source (alongside `media_player → playing` and quiet-hours-end re-eval) that funnels into the same cascade.

#### Scenario: HA restart while music is playing, override was lost mid-restart

- **WHEN** music is playing on `media_player.kitchen_sonos`, the operator runs `ha/deploy.sh` which restarts HA core, and during the restart window Sonos's integration briefly reports `unavailable` so the now-playing-stopped automation flips `active_override` to `schedule` before HA goes down; HA finishes restarting and `media_player.kitchen_sonos` is `playing` again
- **THEN** within seconds of `homeassistant.start`, the new HA-start reconcile automation fires, sees Sonos playing and override == `schedule`, runs the activation cascade, and the override returns to `now_playing` with retained `active_mode = now-playing` republished. The Inkplate's next wake (timer, Poll, or operator tap) draws the now-playing face.

### Requirement: Classical metadata enrichment

When the publisher writes a Sonos input that includes a Spotify `media_content_id`, the renderer SHALL enrich the input with structured metadata before persisting it. The enrichment SHALL produce these fields when sources are reachable:

- `composer` (string) — the canonical Latin form of the composer's name.
- `work` (string) — the work title minus any movement suffix.
- `movement` (string) — the movement designation, when the title contains a movement-shaped suffix.
- `performers` (list of `{ name, role }`) — performers as published by Spotify, ordered as Spotify orders them, with role labels derived from MusicBrainz artist type and disambiguation when available.
- `first_release_year` (string `YYYY`) — the smaller of MusicBrainz's `recording.first-release-date` and Spotify's `album.release_date`.
- `classical` (boolean) — true when the track is classifiable as classical.

A track is classical when any of the following holds:

- MusicBrainz returned a recording with a work-rel that resolves to a work with at least one composer relation; OR
- MusicBrainz returned typed performer disambiguations (`pianist`, `cellist`, `violinist`, `harpsichordist`, `conductor`, `soprano`, `mezzo`, `tenor`, `baritone`, `bass`, etc.) or ensemble types (`Orchestra`, `Choir`, `Group`); OR
- Spotify lists 2+ artists AND the track title matches a catalogue marker (`Op.`, `BWV`, `K.`, `RV`, `TH`, `R.`, `D.`, `L.`, `S.`, `WoO`, `Hob.`, `HWV`) or a known classical form (`Symphony`, `Concerto`, `Sonata`, `Quartet`, `Prélude`, `Étude`, `Nocturne`, `Mazurka`, `Sarabande`, `Allemande`, `Gigue`, `Mass`, `Fugue`, `Suite`, `Variations?`, `Carnival`, `Pieces`, `Songs`, `Romance`, `Lied`, `Gymnopédie`, `Gnossienne`, `Liebestraum`) or a roman/arabic-numeral movement marker after a colon.

When enrichment cannot complete (Spotify unreachable, MB unreachable and Spotify alone insufficient, no Spotify track id), the renderer SHALL persist the original publisher payload unchanged. Renders fall back to the non-classical layout populated from the existing `title`/`artist`/`album` fields.

Enrichment results SHALL be cached on disk indefinitely. Cache keys are the Spotify track id, the ISRC, the MusicBrainz work MBID, and the MusicBrainz artist MBID (for composer aliases). Recording metadata is treated as immutable; no TTL applies.

Spotify's stock edition suffixes on track and album titles (hyphen form `" - 2021 Remaster"`, `" - Live at <venue>"`, `" - Mono Version"`; parenthetical form `"(2011 - Remaster)"`, `"(Deluxe Edition)"`, `"(Anniversary Edition)"`) SHALL be stripped before display in both the classical and non-classical layouts. Stripping is conservative: legitimate hyphenated titles (`"Comfortably Numb - Pulse"`) and legitimate parentheticals (`"Symphony No. 9 (Choral)"`) survive.

#### Scenario: Classical track is enriched on first encounter

- **WHEN** Sonos starts playing a Spotify track for which the operator has not previously seen the renderer enrich, and that track resolves via ISRC to a MusicBrainz recording with a work-rel
- **THEN** within ~800 ms of receiving the publisher payload the renderer has produced an enriched `sonos.json` with `composer`, `work`, optional `movement`, `performers[]` carrying typed roles, `first_release_year`, and `classical: true`. Subsequent encounters of the same track read from cache and complete in under 5 ms.

#### Scenario: Spotify and MusicBrainz both unreachable

- **WHEN** Sonos starts playing a track but Spotify's API and MusicBrainz are both blocked from the renderer host
- **THEN** the renderer persists the original publisher payload without `composer` / `work` / `classical` fields, and Now-Playing renders the non-classical layout using the existing `title` / `artist` / `album` fields.

#### Scenario: Edition suffix is stripped before display

- **WHEN** Sonos plays a track whose Spotify `media_title` is `"Red Right Hand - 2021 Remaster"` from album `"The Boatman's Call (2011 - Remaster)"`
- **THEN** the rendered non-classical layout shows `Red Right Hand` in the work slot and `The Boatman's Call` in the album row; neither field carries the edition suffix.

### Requirement: Composer-anchored layout for classical tracks

When the renderer draws Now-Playing for a track with `classical: true`, the right column SHALL anchor the composer at top, the work in the primary serif slot, the movement (if present) below the work as italic serif, and the performers in a typed list at the bottom. Specifically:

- Composer in mono caps with wide letter-spacing, hairline rule below the line (top label slot).
- Work in Fraunces serif sized adaptively by character count: ≤14 → 48u, ≤22 → 38u, ≤34 → 32u, otherwise 26u with tighter line-height. Wraps to 2 lines naturally; non-breaking thin spaces glue tokens like "No. 8" and "C minor".
- Movement in italic Fraunces at 26u, hidden when empty.
- Performers in mono caps at 24u with optional role chip at 18u in a fixed left column. The role chip is omitted when the performer's type is `Orchestra`, `Choir`, or `Group` (the type is already in the name). Names wrap rather than ellipsise.
- Release year as a small (20u) faint trailing row below the performer list, hidden when no year is known.
- Source indicator (e.g. `SONOS · SPOTIFY`) and clock keep their existing top-corner / bottom-right corner anchors.

#### Scenario: Multi-credit chamber recording renders with typed roles

- **WHEN** the input has `composer = "Erik Satie"`, `work = "Gymnopédie No. 1"`, `movement = ""`, `performers = [{name: "Gautier Capuçon", role: "Cello"}, {name: "Jérôme Ducros", role: "Piano"}, {name: "Orchestre de chambre de Paris", role: ""}, {name: "Adrien Perruchon", role: "Cond."}]`, `first_release_year = "2020"`
- **THEN** the right column renders ERIK SATIE / Gymnopédie No. 1 / (no movement) / four performer rows with chips (`Cello | Gautier Capuçon`, `Piano | Jérôme Ducros`, `Orchestre de chambre de Paris` (no chip — wraps if needed), `Cond. | Adrien Perruchon`) / 2020. No truncation; long ensemble names wrap.

### Requirement: Track-anchored layout for non-classical tracks

When the renderer draws Now-Playing for a track with `classical: false` (or the `classical` field absent), the right column SHALL use the same three-row anatomy as the classical layout, populated as artist / track / album, with year as a separate trailing row:

- Artist (from `sonos.artist` or enriched `performers[0].name`) in the top label slot, mono caps with hairline rule below.
- Track name (from `sonos.title`, with Spotify edition suffixes stripped) in the work slot, Fraunces serif with the same adaptive size buckets as classical.
- Album (from `sonos.album`, with Spotify edition suffixes stripped) in the bottom strip as a single row, mono caps with hairline rule above.
- Release year (from `first_release_year` when available) as a small faint trailing row below the album, matching the year row in the classical layout. Hidden when no year is known.

The layout SHALL match the conventional music-app hierarchy track > artist > album in visual weight. The previously-shipped flat layout (large serif title, mono-caps artist, sans album) is replaced.

#### Scenario: Pop track renders with track in the primary slot

- **WHEN** the input has `title = "Drinking Age"`, `artist = "Cameron Winter"`, `album = "Heavy Metal"`, `first_release_year = "2024"`, `classical = false`
- **THEN** the right column renders CAMERON WINTER (top label) / Drinking Age (big serif) / HEAVY METAL (album row) / 2024 (year row).

### Requirement: Release year selection

When both Spotify's `album.release_date` and MusicBrainz's `recording.first-release-date` are present, the renderer SHALL use the *earlier* year. When only one is present, it SHALL use that one. When neither is present, the year row SHALL be omitted from the layout.

This rule reflects that both sources err towards more-recent dates when their underlying catalogue lacks the original release: Spotify because it returns the active album version's date, MusicBrainz because its volunteer catalogue may only have remasters. Taking the minimum favours whichever source got the original right without privileging either.

#### Scenario: Spotify reports remaster year, MB reports original

- **WHEN** Sonos plays a track whose Spotify `album.release_date` is `"2024-08-23"` (a 2024 half-speed master) and MusicBrainz's `recording.first-release-date` is `"1975"` (the original release)
- **THEN** the rendered year is `1975`.

#### Scenario: MB reports remaster year, Spotify reports original

- **WHEN** Sonos plays a track whose Spotify `album.release_date` is `"2008-09-15"` and MusicBrainz's `recording.first-release-date` is `"2022"` (because MB only catalogues a 2022 reissue of that recording entity)
- **THEN** the rendered year is `2008`.

#### Scenario: Neither source returns a year

- **WHEN** Sonos plays a track for which both `album.release_date` and MusicBrainz's `first-release-date` are absent
- **THEN** the year row is omitted from the layout; the album row in the non-classical layout still renders the album name on its own.

