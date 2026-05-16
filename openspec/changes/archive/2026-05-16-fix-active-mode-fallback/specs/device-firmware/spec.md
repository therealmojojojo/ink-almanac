# device-firmware Specification — delta

## MODIFIED Requirements

### Requirement: Active-mode discovery

On each wake, the device SHALL query HA's active-mode endpoint before fetching any PNG. The endpoint returns the currently-active mode name (one of: `summary`, `weather`, `gallery`, `night`, `now-playing`).

The device SHALL NOT hard-code the schedule. Schedule logic lives in HA; the device trusts HA's answer.

When the retained MQTT read returns an empty payload, the firmware SHALL distinguish two cases:

1. **Cold-boot, before HA has populated the topic**: `wake::Persisted::current_mode == Mode::Unknown`. The firmware SHALL fall back to time-of-day inference (`timeOfDayFallback(hour)` — Summary 06-10, Weather 10-22, Night 22-06) and use the result as the active mode. This is the original cold-boot fallback path.

2. **Steady-state read failure**: `wake::Persisted::current_mode != Mode::Unknown` (i.e. the device has previously drawn a face and knows what's on the panel). The firmware SHALL return `current_mode` and SHALL NOT fall back to time-of-day. A transient broker-delivery delay on a marginal-RSSI link is not a signal that the active mode has changed; the persisted state is the right answer.

The rationale: `mqttReadRetained` is a bounded blocking subscribe-and-wait. On a degraded WiFi link the broker's retained-value delivery occasionally misses the timeout window. The earlier behavior (always falling back to time-of-day on empty) caused spurious face changes during steady-state operation — a hiccup mid-Sonos-session would invent `Weather` and the device would draw it for one wake before the next read succeeded and corrected to `now-playing`. The new behavior keeps the persisted face on screen across the hiccup.

#### Scenario: HA reports gallery (steady-state, normal read)

- **WHEN** the device wakes at 14:00, queries HA's retained `active_mode` topic, and receives `gallery`
- **THEN** the firmware uses `gallery` as the active mode and fetches `/display/gallery.png`

#### Scenario: HA reports now-playing (steady-state, normal read)

- **WHEN** the device wakes after receiving an HA wake signal, queries HA, and receives `now-playing`
- **THEN** the firmware uses `now-playing` as the active mode and fetches `/display/now-playing.png`

#### Scenario: Cold-boot fallback when HA hasn't published yet

- **WHEN** the device cold-boots, brings up MQTT, and reads an empty retained payload at `inkplate/command/active_mode`; `current_mode` is `Mode::Unknown` because no prior Full has succeeded
- **THEN** the firmware falls back to `timeOfDayFallback(local_hour)` and uses that mode for this wake's Full draw; after the draw succeeds, `current_mode` is updated and subsequent wakes will hit the steady-state path

#### Scenario: Steady-state read hiccup preserves current_mode

- **WHEN** the device is in `now-playing` mode mid-Sonos-session (`current_mode == NowPlaying`), wakes for a Poll, brings up MQTT, calls `mqttReadRetained(active_mode)` and receives an empty payload because the broker's retained-value delivery missed the 800 ms wait window (marginal RSSI, broker overload, etc.)
- **THEN** the firmware returns `current_mode == NowPlaying` (NOT `timeOfDayFallback(hour)`); the Poll's mode-change-promotion sees `NowPlaying == NowPlaying`, no promotion fires, the device sleeps after a partial clock tick. The panel stays on Now-Playing across the hiccup; the next Poll's read typically succeeds and confirms the mode

#### Scenario: Boot with network unreachable

- **WHEN** the device cold-boots and WiFi fails to associate
- **THEN** `mqttConnect` returns false, the Poll/Full paths bail before reaching `resolveActiveMode`, the firmware uses the cached `zones.json` from flash, falls back to the time-of-day mode inference for the active mode (via `current_mode == Unknown` triggering the time-of-day path), renders the error status glyph, and continues to local-tick on subsequent wakes until network returns
