# device-firmware Specification

## Purpose
TBD - created by archiving change add-device-simulation. Update Purpose after archive.
## Requirements
### Requirement: HAL-based structure

The firmware SHALL route all hardware interactions through interface-based abstractions (the Hardware Abstraction Layer, defined by `device-simulation`). The main loop, wake-handling, override management, door-filter logic, and power-budget accounting SHALL reference HAL interfaces rather than concrete hardware libraries.

Concrete on-device implementations live in `firmware/src/hal/real/`. Mock implementations for simulation live in `firmware/test/hal/mock/`. The same firmware sources compile against either.

#### Scenario: Refactor preserves behavior

- **WHEN** the HAL-based firmware is flashed to the Inkplate and runs through each scenario from `device-firmware` and `device-wake-protocol`
- **THEN** behavior is identical to a hypothetical direct-call implementation; the refactor is purely structural

#### Scenario: Hardware library dependency attempt outside HAL

- **WHEN** a code change adds `#include <Inkplate.h>` in a non-HAL file
- **THEN** a pre-commit or CI check flags the import as a HAL-boundary violation

### Requirement: Thin-client main loop

The device's firmware main loop SHALL be a thin fetch-and-display cycle:

1. Wake from deep sleep.
2. Identify the wake source: `cold_boot`, `post_ota`, `timer`, `local_tick`, `imu`, `ha_command`, or `sonos_fast_path`.
3. **If reason is `local_tick`:** read the external RTC, draw the clock (or Night approximate-phrase) into the active face's clock zone using firmware-shipped bitmap glyphs, perform a partial refresh of that rectangle, and return to deep sleep. Do NOT connect WiFi or MQTT. Do NOT publish `state/device`. If `partial_refresh_count >= kGhostClearPartialCount`, promote this wake to a full-cycle refresh instead (go to step 4).
4. Connect WiFi + MQTT. Query HA's retained `active_mode`.
5. If the active mode differs from the last-drawn mode, fetch `GET /display/{mode}.png` from the renderer and perform a **full refresh**. Reset `partial_refresh_count`.
6. If the active mode matches the last-drawn mode AND this is a full-cycle wake (not `local_tick`), fetch the same URL and perform a **full refresh** (so the clock zone is repainted authoritatively alongside any other data updates). Reset `partial_refresh_count`.
7. Publish battery percentage and voltage to HA via `state/device`.
8. Arm wake sources for the next sleep per the sleep-strategy table; deep sleep.

#### Scenario: Local-tick wake during Summary hours

- **WHEN** the device wakes at 08:47 with `Reason::LocalTick`, active mode is Summary (unchanged since last wake), and `partial_refresh_count = 12`
- **THEN** the device reads the external RTC, draws `08:47` into the Summary clock zone via firmware-shipped digit glyphs, performs a partial refresh of the clock rectangle, increments `partial_refresh_count`, arms the next 1-min `LocalTick` and the next 15-min full-fetch timer, and returns to deep sleep. No WiFi, no MQTT, no state publication.

#### Scenario: Local-tick promotes to full-cycle on ghost-clear boundary

- **WHEN** the device wakes with `Reason::LocalTick` and `partial_refresh_count = 30`
- **THEN** instead of partial-refreshing, the device executes the full-cycle path (WiFi, MQTT, fetch PNG, full refresh), resets `partial_refresh_count` to 0, and publishes `state/device`.

#### Scenario: Full-cycle wake during Gallery hours

- **WHEN** the device wakes at 14:00 with `Reason::Timer` (the 15-min full-fetch timer), active mode is Gallery
- **THEN** the device connects WiFi + MQTT, reads retained `active_mode = gallery`, fetches `/display/gallery.png`, performs a full refresh (resetting `partial_refresh_count`), publishes `state/device`, and arms the next full-fetch timer + next `LocalTick` before sleeping.

#### Scenario: Mode change on full-cycle wake

- **WHEN** the device wakes at 10:00 with `Reason::Timer` and the retained `active_mode` has changed from `summary` to `gallery`
- **THEN** the device fetches `/display/gallery.png`, performs a full refresh, updates the last-drawn mode, resets `partial_refresh_count`, and any visible status glyph is implicitly cleared by the repaint.

### Requirement: Sleep strategy

The firmware SHALL follow a unified sleep-and-wake strategy that coordinates local-tick cadence, full-fetch cadence, armed wake sources, and fast-path responsiveness across modes and time-of-day. The policy is defined by the following table; any future changes to timers or wake sources SHALL update this table.

| Period | Hours (default) | Mode | Local-tick cadence | Full-fetch cadence | Sonos fast-path | IMU INT armed | HA wake on MQTT observed |
|---|---|---|---|---|---|---|---|
| Morning | 06:30–10:00 | Summary | 1 min | 15 min | 3 min (after 07:00) | yes | on next natural wake |
| Daytime | 10:00–20:00 | Gallery | 1 min | 15 min | 3 min | yes | on next natural wake |
| Evening | 20:00–22:00 | Gallery | 1 min | 30 min | disabled | yes | on next natural wake |
| Night | 22:00–06:30 | Night | 15 min (aligned to `:00 / :15 / :30 / :45`) | 60 min | disabled | yes | on next natural wake |
| Now-Playing (within Sonos hours) | variable | Now-Playing | — (no local-tick; clock is secondary on this face) | 15 min | — | yes | immediate (device is already awake during fast-path polls) |

Configurable parameters with defaults:

- `sonos_active_start` — default `07:00`.
- `sonos_active_end` — default `20:00`.
- `quiet_start` — default `00:00`. Used by HA to gate motion-driven wake pulses (not by the device directly).
- `quiet_end` — default `05:00`.
- `fast_path_interval` — default `180` seconds.
- `local_tick_day_sec` — default `60`.
- `local_tick_night_sec` — default `900` (aligned to the quarter-hour boundary at arming time).
- Per-mode full-fetch intervals.

All parameters SHALL be editable via `config.h` or, where appropriate for runtime tuning (Sonos hours, quiet hours, cadences), via HA input helpers read over MQTT on wake.

Strategy notes:

- **Local-tick cadence** is the local-draw cycle — no network, partial refresh of the clock zone (or Night approximate-phrase zone) only.
- **Full-fetch cadence** is the full-cycle refresh for data freshness and ghost-clear. Full fetches always paint the whole face, which authoritatively repaints the clock zone.
- **Ghost-clear cadence** is an escape hatch: when `partial_refresh_count >= kGhostClearPartialCount` (default 30), the next `LocalTick` is promoted to a full-cycle refresh regardless of whether the full-fetch timer was ready.
- **Sonos fast-path timer** is unchanged from the prior revision; still only active within the configured Sonos window.
- **IMU INT always armed** — a deliberate tap at 03:00 SHALL still work.
- **Now-Playing has no local-tick** — the Now-Playing face's clock area is subordinate to album art, and track changes arrive via HA; a minute-tick clock is not the primary UX on that face.

#### Scenario: Morning local-tick sequence

- **WHEN** the device is in Summary mode; last full fetch was at 08:45, last local-tick at 08:46
- **THEN** at 08:47 the `LocalTick` timer fires, the device draws `08:47` into the clock zone, partial-refreshes, sleeps, and arms the next `LocalTick` at 08:48 plus the next full-fetch timer at 09:00

#### Scenario: Day full-fetch sequence

- **WHEN** the device is in Gallery mode; last full fetch was at 14:00, now is 14:15
- **THEN** the full-fetch timer fires, the device performs a full-cycle refresh (connect, fetch, full refresh, publish state), and arms the next full-fetch at 14:30 plus continues `LocalTick` every minute

#### Scenario: Night quarter-tick

- **WHEN** the device is in Night mode; time is 02:30
- **THEN** the `LocalTick` timer fires, `nightPhrase(2, 30)` returns "half past two", the device draws that phrase into the Night phrase zone, partial-refreshes, and arms the next `LocalTick` at 02:45

#### Scenario: Cold boot

- **WHEN** the device cold-boots
- **THEN** the device reads the external RTC (via PCF85063A), attempts a WiFi + NTP sync (and, on success, writes the synced epoch back to the RTC), fetches `zones.json` (caching to flash), reads retained `active_mode`, fetches and full-refreshes the corresponding face, publishes `state/device` with `wake_reason: cold_boot`, and arms the mode's timers before entering deep sleep

#### Scenario: Boot with network unreachable

- **WHEN** the device cold-boots and WiFi fails to associate
- **THEN** the device reads the external RTC (populated from coin-cell-backed history), uses the cached `zones.json` from flash, falls back to the time-of-day mode inference for active-mode, renders the error status glyph, and continues to local-tick on subsequent wakes until network returns

### Requirement: Wake sources

The device SHALL arm the following wake sources on each deep-sleep entry:

- **LocalTick wake** — a dedicated timer for the local-draw cadence. Day: 1 min. Night: 15 min (aligned to the quarter). Does NOT connect the network. Distinct from `Timer` so that the main loop can branch on intent.
- **Full-fetch timer** — the mode's own network refresh cycle. Per the sleep-strategy table.
- **Sonos fast-path timer** — unchanged from prior revisions; 3 min during the Sonos window.
- **LSM6DSO INT wake** — GPIO connected to the IMU's INT1 pin, configured with hardware tap-detect. (Hardware assembly: `add-device-firmware §5.4`. If the INT1 wire is not in place, tap detection degrades to latched-polling on every wake, bounded by the LocalTick cadence.)
- **HA wake** — the mechanism defined by `device-wake-protocol` (MQTT retained active_mode + `inkplate/command/wake` pulse). HA-initiated wakes subsume motion (via `ha-integrations` IKEA sensor) and schedule transitions.

The device SHALL NOT arm a dedicated PIR wake source. Motion detection lives in HA (per `move-pir-to-ha-motion`).

#### Scenario: Gallery daytime wake arming

- **WHEN** the device enters deep sleep in Gallery mode at 14:05
- **THEN** the armed wake sources are the LocalTick timer (60 s), the full-fetch timer (to fire at 14:15), the Sonos fast-path timer (3 min, within the Sonos window), IMU INT, and HA wake via the retained active_mode topic

#### Scenario: Night wake arming

- **WHEN** the device enters deep sleep in Night mode at 02:17
- **THEN** the armed wake sources are the LocalTick timer (set to fire at 02:30, the next quarter), the full-fetch timer (to fire at 03:00), IMU INT, and HA wake; the Sonos fast-path is NOT armed (outside Sonos window)

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

### Requirement: Tap detection

The firmware SHALL treat taps as wake signals only, not as policy decisions. On an `IMU` wake the firmware SHALL:

1. Identify the tap kind (single / double) by reading the LSM6DSO's `TAP_SRC` register.
2. Apply the gyroscope door-filter to suppress false positives from fridge-door rotations.
3. Immediately partial-refresh the `ack` status glyph to acknowledge the tap (see "Status glyphs").
4. Publish the gesture to `inkplate/state/gesture` with `{ "kind": "single" | "double" }`.
5. Read the retained `inkplate/command/active_mode` — which may or may not reflect HA's post-gesture decision yet — and proceed with the normal fetch-and-refresh path.

The firmware SHALL NOT interpret tap kinds as semantic actions (it does NOT "activate Weather peek" or "toggle Summary/Gallery"). Those decisions live in HA's override state machine (see `ha-integrations` override-precedence and the gesture-driven branches in HA's face-selection state machine). HA receives the gesture, consults its full state (Sonos, override precedence, quiet hours, schedule), decides what the new active mode should be, and publishes the retained `active_mode` topic.

To bound tap-to-face-change latency, the firmware SHALL, after publishing the gesture, subscribe to `inkplate/command/active_mode` for a short grace window (default 2 seconds) and prefer any message received within that window over the pre-gesture retained value. If no message arrives in-window, the firmware proceeds with the retained value it read earlier; HA's decision will be picked up on the next natural wake.

This yields the following user-visible timing (assuming the INT1 wire from `add-device-firmware §5.4` is in place):

- ~1 s: `ack` glyph visible
- ~3–5 s: post-publish grace window closes; device reads final `active_mode`
- ~5–10 s: full-refresh completes, showing the face HA decided on

If HA fails to process the gesture in the grace window (rare: HA restart, MQTT delay), the tap is effectively lost for the current wake; the face the device draws is the pre-gesture one. The user sees the ack glyph but no subsequent face change — which is honest UX (we heard you, but nothing changed) and aligns with the rest of the system's "HA owns policy" stance.

#### Scenario: Single tap during Summary hours

- **WHEN** a single tap occurs at 09:00 and HA's state machine decides to activate Weather peek
- **THEN** the device (a) partial-refreshes the ack glyph, (b) publishes `{ "kind": "single" }` to `state/gesture`, (c) waits up to 2 s for an updated `active_mode`, (d) reads `active_mode = weather`, (e) fetches `/display/weather.png` and full-refreshes

#### Scenario: Single tap during quiet hours (HA suppresses)

- **WHEN** a single tap occurs at 02:30 and HA's state machine suppresses Weather peek (quiet-hours rule)
- **THEN** the device (a) shows the ack glyph, (b) publishes the gesture, (c) waits up to 2 s during which HA does NOT change `active_mode`, (d) reads `active_mode = night` (unchanged), (e) either skips the fetch (mode unchanged) or performs the normal full-cycle refresh per the ordinary branch — the Night face remains visible; the user sees ack without a mode change

#### Scenario: Double tap during Gallery hours

- **WHEN** a double tap occurs during Gallery hours and HA's state machine toggles to Summary
- **THEN** the device publishes `{ "kind": "double" }`, reads the updated `active_mode = summary` within the grace window, fetches `/display/summary.png`, and full-refreshes

#### Scenario: Tap during a fast-path or full-cycle wake

- **WHEN** a tap fires while the device is already awake in the middle of a non-IMU wake
- **THEN** the LSM6DSO latches the tap in `TAP_SRC`; before sleeping, the firmware drains `TAP_SRC`, upgrades the wake semantically to IMU, shows the ack glyph, publishes the gesture, and re-reads `active_mode` — the tap is not lost

### Requirement: Battery reporting

On each wake cycle, the device SHALL read its battery voltage, convert to percentage using the Inkplate library's helper or a standard LiPo curve, and report both values to HA via an MQTT topic or an HTTP POST (implementer choice).

#### Scenario: Battery report

- **WHEN** the device wakes and reads 3.78V battery
- **THEN** the device publishes approximately `{ voltage: 3.78, percentage: 62 }` to HA's device-state channel

### Requirement: Power budget

The device firmware SHALL meet the following power-budget targets on a fully charged 5000mAh LiPo:

- Active-hours wake time ≤ 30 seconds per hour on average (06:30–23:00)
- Night-hours wake time ≤ 10 seconds per hour on average (23:00–06:30), assuming minute-tick disabled or aggressively batched
- Overall target: ≥ 6 weeks between charges under normal use (defined as: one daily mode transition, ~5 PIR-triggered wakes per day, ~2 tap events per day, no Now-Playing sessions)

A power-budget estimate SHALL be documented in `firmware/docs/power-budget.md` with back-of-envelope math for each wake type's Ah cost.

#### Scenario: Estimate validates

- **WHEN** the power-budget document is read
- **THEN** the total calculated Ah draw per 24-hour cycle multiplied by 42 days ≤ 5000 mAh (the battery capacity)

### Requirement: Ghost-clear cadence

After every N consecutive partial refreshes in a single mode (default N=30), the next refresh SHALL be a full refresh regardless of whether the mode changed. This clears ghosting accumulation from the minute-region partial updates.

#### Scenario: 31st Night-mode minute tick

- **WHEN** Night mode has performed 30 consecutive partial refreshes for the minute digit and the 31st minute tick fires
- **THEN** the refresh is a full refresh of the entire Night face, resetting the partial counter

### Requirement: Error handling

The firmware SHALL handle server-side unreachability without blanking the display or failing silently.

When the renderer is unreachable on a full-cycle wake (timeout, connection refused, 5xx):

- The device SHALL NOT blank the display; the last rendered face remains visible.
- The `error` status glyph SHALL appear in the top-right status-slot rectangle, overlaying the battery indicator (see "Status glyphs" requirement).
- The device SHALL retry with back-off: 30s, 1min, 5min, 15min, 30min, capped at 30min.
- Once reachability is restored, the `error` status glyph is cleared on the next successful full fetch (which repaints the whole face, including the battery indicator).
- Subsequent `LocalTick` wakes between failure and recovery continue to run (clock stays correct); only the network part is retried.

Similarly, when HA's retained `active_mode` is unavailable:

- The device SHALL fall back to a mode determined by the current local time per the schedule (06:30–10:00 Summary, 10:00–22:00 Gallery, 22:00–06:30 Night).
- The `error` status glyph appears.

#### Scenario: Renderer briefly unreachable

- **WHEN** a fetch fails with a connection timeout at 14:30
- **THEN** the current face remains visible, the `error` glyph appears in the top-right status-slot (hiding the battery indicator for the duration of the error state), the device retries after 30s; LocalTick wakes during the outage still draw the clock locally (no network needed)

### Requirement: OTA updates

The firmware SHALL support over-the-air firmware updates via a standard ESP32 OTA mechanism (ArduinoOTA or HTTP-based). OTA SHALL be authenticated by a shared secret configured in `secrets.h`.

#### Scenario: OTA upload from dev machine

- **WHEN** the operator publishes a new firmware build via OTA
- **THEN** the device downloads and applies it on the next connected cycle, and a notification is sent to HA confirming the new build version

### Requirement: Secrets handling

All device-local credentials and URLs SHALL live in `firmware/include/secrets.h`, which is gitignored. A `secrets.h.example` SHALL be committed showing the expected fields with placeholders.

#### Scenario: Accidental commit of secrets

- **WHEN** the operator stages `firmware/include/secrets.h` to git
- **THEN** the `.gitignore` rule prevents the stage (or the pre-commit hook rejects it)

### Requirement: Local-tick rendering

The device SHALL render the clock (and Night approximate-time phrase) locally from the external RTC, without network access, on every LocalTick wake.

- The clock-zone rectangle for the active face SHALL be read from a cached `zones.json` snapshot fetched on cold boot from the renderer (see "Zones bootstrap" below).
- For the Summary, Weather, and Gallery-visual faces the local-tick renders `HH:MM` using the `ClockDigits` bitmap font shipped in firmware flash. The font set is generated at firmware build time from the renderer's pinned TTF so typography matches the renderer's full-refresh output.
- For the Night face the local-tick renders the phrase returned by `nightPhrase(h, m)` using the `NightText` bitmap font. Night-tick wakes are scheduled to fire aligned to `:00 / :15 / :30 / :45`.
- Local-tick wakes SHALL NOT publish to `state/device`, SHALL NOT connect WiFi or MQTT, and SHALL NOT fetch the renderer.
- Ghost-clear cadence applies: when `partial_refresh_count` reaches `kGhostClearPartialCount` on a LocalTick wake, the firmware SHALL promote that wake to a full-cycle refresh instead.

The Night-phrase algorithm:

```
nightPhrase(h, m):
  hour12     = ((h + 11) mod 12) + 1
  nextHour12 = (hour12 mod 12) + 1
  if m in  0..14: return "{word(hour12)} o'clock"
  if m in 15..29: return "quarter past {word(hour12)}"
  if m in 30..44: return "half past {word(hour12)}"
  if m in 45..59: return "quarter to {word(nextHour12)}"
```

`word(h12)` maps `1..12` to `"one" ... "twelve"`. The algorithm SHALL be implemented identically in the renderer and the firmware; divergence is a spec violation.

#### Scenario: Day local-tick draws precise time

- **WHEN** `Reason::LocalTick` fires at 14:37 with active mode `gallery`
- **THEN** the device reads the external RTC, draws `14:37` into Gallery's clock zone using `ClockDigits` glyphs, and partial-refreshes only that rectangle

#### Scenario: Night local-tick draws phrase

- **WHEN** `Reason::LocalTick` fires at 02:15 with active mode `night`
- **THEN** `nightPhrase(2, 15)` returns "quarter past two"; the device draws that phrase into Night's phrase zone using `NightText` glyphs, and partial-refreshes only that rectangle

#### Scenario: Local-tick with stale zones cache suppresses draw

- **WHEN** `Reason::LocalTick` fires but no `zones.json` snapshot has ever been successfully fetched (first cold boot with network down)
- **THEN** the device skips the local-draw (the clock zone is unknown), arms the next LocalTick, and sleeps; the face remains as last painted until a full-cycle wake can succeed

### Requirement: Status glyphs

The device SHALL use the top-right status-slot rectangle — the same area the renderer paints the battery indicator into — as the "status glyph" slot. At most one glyph is visible at a time. When no glyph is active, the battery indicator painted by the renderer's last full refresh is visible there.

Defined glyphs:

- `ack` — stylized thumbs-up bitmap (~32×32u). Drawn on `Reason::IMU` wake immediately after the tap is identified, BEFORE any network activity. Cleared implicitly by the next full refresh of the face.
- `error` — stylized warning triangle bitmap (~32×32u). Drawn whenever a full-cycle fetch fails (renderer unreachable, 5xx, timeout) or the retained `active_mode` topic cannot be read. Cleared on the next successful full fetch.

Both glyphs are pre-rendered monochrome bitmaps shipped in firmware flash (`firmware/include/assets/glyphs/`). The slot rectangle is declared in `zones.json` as `faces.<mode>.status_slot`; firmware reads it from the cached snapshot.

**Overlay behavior:** drawing a status glyph partial-refreshes the glyph bitmap over the rectangle that currently holds the rendered battery indicator. While the glyph is visible, the battery indicator is hidden. On the next full-cycle refresh of the face (triggered by mode change, schedule boundary, ghost-clear promotion, or a successful retry after an error), the whole face — including the battery indicator — is repainted, which implicitly clears the glyph. Users needing live battery telemetry consult HA, which receives it via `state/device`; the on-face indicator remains a glanceable affordance whose brief occlusion during an ack flash or error state is acceptable.

When both `ack` and `error` conditions are simultaneously true (rare: tap during an outage), `error` wins — the user needs to know the system is degraded more than they need acknowledgement.

The previously-specified corner indicator for renderer unreachability ("a small circle in the battery area, 6u square") SHALL be retired; its role is subsumed by the `error` glyph, at the same location and larger so it reads at kitchen viewing distance.

#### Scenario: Ack glyph on tap

- **WHEN** the device wakes with `Reason::IMU` at 09:10, the IMU reports a single-tap
- **THEN** within ~1.5 s of the tap, the device partial-refreshes the top-right status-slot rectangle with the `ack` glyph (covering the battery indicator), then proceeds to the network round-trip; the subsequent full refresh restores the battery indicator and clears the glyph

#### Scenario: Error glyph on fetch failure

- **WHEN** the device wakes with `Reason::Timer` at 14:30 and the renderer's `/display/gallery.png` returns connection-refused
- **THEN** the device partial-refreshes the top-right status-slot with the `error` glyph (covering the battery indicator for the duration of the outage), keeps the last-drawn face on screen, schedules a retry, and continues to run LocalTick wakes between now and retry

#### Scenario: Full refresh restores the battery indicator

- **WHEN** the device has the `error` glyph visible and a subsequent full-cycle fetch succeeds
- **THEN** the full refresh repaints the entire face, which implicitly clears the glyph and repaints the battery indicator in the status-slot rectangle; no explicit clear call is required

### Requirement: External RTC primary clock

The firmware SHALL use the on-board PCF85063A external RTC as the primary time source.

- On cold boot, the device reads the PCF85063A over I²C to obtain the current epoch.
- After a successful WiFi association and NTP sync, the firmware SHALL write the synced epoch back to the PCF85063A so it stays accurate long-term.
- When the PCF85063A is unreachable (I²C failure, chip missing), the firmware falls back to the ESP32 internal RTC and continues; a diagnostic flag in `state/device` surfaces the fallback to HA.
- The CR2032 coin-cell battery that backs the PCF85063A is a required install step (see `add-physical-build`); without it, the external RTC loses time on main-battery power events.

The external RTC eliminates the "wrong clock after hard reset" UX failure mode that would otherwise block the local-tick architecture from rendering a correct clock before NTP completes.

#### Scenario: Boot after battery swap

- **WHEN** the main LiPo is disconnected for 10 minutes and reconnected
- **THEN** the device cold-boots, reads the PCF85063A (which kept ticking from the coin cell), and the first LocalTick wake draws the correct time even before WiFi associates

#### Scenario: PCF85063A unreachable

- **WHEN** I²C communication with the PCF85063A fails at boot
- **THEN** the firmware falls back to the ESP32 internal RTC, publishes `{ "rtc_source": "internal" }` in `state/device`, and still proceeds with the normal boot flow; local-tick draws whatever the internal RTC reports

### Requirement: Zones bootstrap

On cold boot and post-OTA boot, the firmware SHALL fetch `GET /display/zones.json` from the renderer and cache the body plus its `version` hash to flash storage.

- If the fetch succeeds, the firmware persists the new snapshot and records the version hash in RTC SRAM.
- If the fetch fails and a prior snapshot exists in flash, the firmware uses the prior snapshot (last-known-good).
- If the fetch fails and no prior snapshot exists, local-tick rendering is suppressed until a future cold boot succeeds; the face continues to render on full-cycle wakes (which use server-side layout regardless).
- Mid-session (non-cold-boot) wakes use the RTC-SRAM version marker to avoid re-reading flash; they read coords from the cached snapshot directly.

#### Scenario: Zones fetch succeeds at cold boot

- **WHEN** the device cold-boots, connects WiFi, and receives zones.json with version `sha256:abc123`
- **THEN** the body is persisted to flash, the version hash is stored in RTC SRAM, and subsequent LocalTick wakes use the new coordinates

#### Scenario: Zones fetch fails with prior cache

- **WHEN** the device cold-boots, WiFi fails, but a prior zones.json snapshot exists in flash with version `sha256:xyz789`
- **THEN** the firmware uses the prior snapshot; the `error` status glyph is drawn on the next face render until a successful full fetch occurs



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
