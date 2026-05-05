# device-firmware Specification — delta

## ADDED Requirements

### Requirement: NowPlaying mode uses Poll cadence with track-change promotion

When the active mode is NowPlaying, `fw::wake::pathForMinute()` SHALL return `Path::Poll` (not `Path::Full`) for every minute. The wake cadence stays at one minute (`minutes_to_next_wake == 1`); the wake's *work* changes from a full-refresh-every-minute to a network-only Poll, with promotion to Full only when the operator-relevant content has actually changed.

The Poll handler in `tick()` SHALL, when the resolved active mode is NowPlaying and no mode-change-promotion has already fired this wake, read the retained MQTT payload at `inkplate/state/now_playing_track`. The handler SHALL:

- Short-circuit on empty payload — no hash computation, no diag flag, no promotion to Full.
- On non-empty payload, compute `fnv32(payload)` (the same FNV-32 routine used for the wake-schedule topic) and compare against `wake::Persisted::sonos_track_hash`.
- On hash mismatch, promote this Poll to a Full via the existing `doFull(...)` call with `already_resolved = NowPlaying`. The hash cache is NOT updated by the Poll itself; `doFull` updates the cache after a successful draw.
- On hash match, return to deep sleep without further work.

#### Scenario: Steady-state Sonos session — most minutes are cheap Polls

- **WHEN** the device is in NowPlaying mode and the operator plays a 4-minute song through Sonos with no track change
- **THEN** the firmware records 4 wakes in the diag ring; the first wake (the entry into NowPlaying) is a Full; the remaining 3 are Polls (`Path::Poll`); none of the 3 Polls promotes to Full because the retained track topic's hash matches the cached `sonos_track_hash`

#### Scenario: Track change promotes the next Poll to a Full

- **WHEN** the device is in NowPlaying mode with `sonos_track_hash` populated for "track A", and HA publishes a new payload for "track B" to `inkplate/state/now_playing_track` (retained)
- **THEN** the next minute's Poll wake reads the retained payload, computes a hash that differs from the cached value, promotes itself to a Full via `doFull`, fetches `/display/now-playing.png` (which the renderer has already regenerated for track B), draws the new face, and updates `persisted.sonos_track_hash` to track B's hash before returning to sleep

#### Scenario: Empty retained payload is a no-op

- **WHEN** the device enters NowPlaying mode but the broker has no retained value at `inkplate/state/now_playing_track` (fresh broker, Sonos never played, or operator-cleared topic)
- **THEN** the Poll handler reads an empty string and short-circuits; `sonos_track_hash` is NOT updated; the wake records a `Path::Poll` diag entry with no track-change promotion; the device returns to sleep without re-fetching the renderer

### Requirement: `doFull` caches the track hash when drawing NowPlaying

After a successful Full draw with `active_mode == NowPlaying`, `doFull` SHALL read `inkplate/state/now_playing_track` and update `wake::Persisted::sonos_track_hash` to `fnv32(payload)` when the payload is non-empty. Empty payloads leave the cache untouched.

The cache update SHALL happen AFTER `wake::persisted().current_mode = active`, so a re-entrant call sees the correct mode, but BEFORE the device returns to deep sleep.

#### Scenario: Cold boot into NowPlaying does not double-draw

- **WHEN** the device cold-boots with `active_mode = now-playing` retained on the broker (e.g., HA pushed it before the device's flash), and the broker also has a non-empty retained `now_playing_track` payload
- **THEN** the cold-boot Full draws the Now-Playing face and reads the track topic, populating `sonos_track_hash` before returning to sleep. The next Timer wake's Poll reads the same payload, finds a matching hash, and does NOT promote — the panel is drawn exactly once for this track entry, not twice

#### Scenario: Failed Full leaves the cache stale, next Poll retries

- **WHEN** a Poll detects a track-hash mismatch and calls `doFull`, but the renderer fetch fails (timeout, 404, network down) and no draw lands
- **THEN** `doFull`'s cache update step still runs (since `current_mode` still flips to NowPlaying for any successful MQTT path; if MQTT was the failure point, current_mode does NOT change). On a subsequent wake when MQTT recovers, the next Poll's track-hash check fires again because the cache was either left at the old value or updated to the new track. Either way, the operator's track change is eventually reflected — the firmware does not "lose" the change.

### Requirement: `Persisted` carries `sonos_track_hash` across deep sleep

`fw::wake::Persisted` SHALL include a `uint32_t sonos_track_hash` field, initialised to 0, persisted across deep sleep in RTC slow memory. Zero is the sentinel for "uninitialised / no track yet". The Poll handler's empty-payload short-circuit ensures the cache is never set to `fnv32("") = 0x811c9dc5`, so a non-zero cached value always means "a real track was seen here previously".

#### Scenario: Persisted hash survives normal deep sleep

- **WHEN** the device draws Now-Playing for track A, deep-sleeps, wakes 60 seconds later for a Poll
- **THEN** the cached hash is still track A's; the Poll reads the (unchanged) retained topic, hashes match, no promotion

### Requirement: Session-aware NowPlaying cadence override

`fw::wake::pathForMinute` SHALL return `Path::Poll` when EITHER of the following is true:

1. `wake::Persisted::session_now_playing == true` (HA's `input_text.inkplate_active_override` is `now_playing`, regardless of which face the device is currently displaying), OR
2. `mode == fw::modes::Mode::NowPlaying` (cold-boot fallback, before the override topic has been read).

This decouples the per-minute Poll cadence from the visible face. During a tap-peek, `active_mode` briefly flips to a peek face (Summary/Gallery) while HA's session state stays `now_playing`; the device must continue per-minute Polls so it catches the peek-revert (HA publishing `active_mode = now-playing` again at the end of the peek window) within ≤60 s.

The session flag SHALL be updated on every Full/Poll/PollPartial wake from the retained MQTT topic `inkplate/state/active_override`. Empty payload leaves the flag untouched (no signal); any non-empty payload sets the flag to `(payload == "now_playing")`. The `mode == NowPlaying` clause in the override condition is a fallback for the first wake after a cold boot when the override topic hasn't been read yet.

#### Scenario: Tap-peek during music keeps per-minute cadence

- **WHEN** the device is in NowPlaying mode (session flag true, active_mode `now-playing`), and the operator double-taps the panel; HA's tap-peek automation publishes `active_mode = summary` retained AND `active_override` stays `now_playing`
- **THEN** the device's IMU wake → tap-Full draws Summary; subsequent Timer wakes consult `pathForMinute` with `mode = Summary` and `session_now_playing = true` → still return Poll → wakes continue at one-minute cadence; when HA publishes `active_mode = now-playing` again 60 s later, the next Poll's mode-change detection (≤60 s after the peek revert) promotes to Full and draws Now-Playing

#### Scenario: Session ends → revert to tier cadence

- **WHEN** Sonos pauses, HA's linger timer expires, and HA publishes `active_override = schedule` AND `active_mode = <scheduled face>` retained
- **THEN** the device's next Full/Poll/PollPartial wake reads the override topic, sets `session_now_playing = false`; the same wake's `resolveActiveMode` detects the mode change and promotes to Full to draw the scheduled face; the post-tick `plannedSleepSec` consults `pathForMinute` with `session_now_playing = false` and `mode = <scheduled face>` → returns the tier's cadence (which under the operator's "no daytime Polls" config means Fulls + Partials only); from this point the device follows the tier's cadence until the next session

#### Scenario: Cold-boot fallback when override topic unread

- **WHEN** the device cold-boots into a state where the broker has `active_mode = now-playing` retained but the override topic hasn't been read yet (or the device's first Full hasn't completed)
- **THEN** the cold-boot Full path forces a Full draw regardless (existing behavior); for the immediate-next sleep, `pathForMinute` consults the cached state — `session_now_playing` is false but `mode == NowPlaying` is true → returns Poll → device sleeps 60 s; on its next wake, the Poll reads the override topic and sets the session flag canonical, after which the mode-check is redundant

#### Scenario: Empty override topic leaves the flag untouched

- **WHEN** the device wakes, brings up MQTT, and reads `inkplate/state/active_override` returning empty (broker has no retained value, e.g., HA is down)
- **THEN** the firmware short-circuits and does NOT update `session_now_playing`; the cached value (whatever was last successfully read) remains in effect; if the broker recovers and the topic is repopulated, the next wake picks up the new value normally
