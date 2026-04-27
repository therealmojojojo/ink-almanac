## ADDED Requirements

### Requirement: Thin-client main loop

The device's firmware main loop SHALL be a thin fetch-and-display cycle:

1. Wake from deep sleep.
2. Identify the wake source (timer, PIR, IMU INT, HA wake).
3. Query HA for the currently-active mode.
4. If the active mode differs from the last-drawn mode, fetch `GET /display/{mode}.png` from the renderer and perform a **full refresh**.
5. If the active mode matches the last-drawn mode AND a partial-refresh condition applies (minute tick in Summary/Night), fetch the same URL and perform a **partial refresh** of the minute region.
6. Report battery percentage and voltage to HA.
7. Arm wake sources; deep sleep.

#### Scenario: Mode change wake

- **WHEN** the device wakes at the 10:00 schedule transition and the active mode advances from `summary` to `gallery`
- **THEN** the device fetches `/display/gallery.png`, performs a full refresh, updates stored last-drawn mode, reports battery, and returns to deep sleep

#### Scenario: Minute-tick wake in Summary

- **WHEN** the device wakes at HH:M0 during Summary hours, active mode is unchanged
- **THEN** the device fetches `/display/summary.png`, performs a partial refresh on the clock's bounding rectangle only, and returns to deep sleep

### Requirement: Sleep strategy

The firmware SHALL follow a unified sleep-and-wake strategy that coordinates timer cadence, armed wake sources, and fast-path responsiveness across modes and time-of-day. The policy is defined by the following table; any future changes to timers or wake sources SHALL update this table.

| Period | Hours (default) | Mode | Timer cadence | Sonos fast-path timer | PIR armed | IMU INT armed | HA wake on MQTT observed |
|---|---|---|---|---|---|---|---|
| Morning | 06:30–10:00 | Summary | 15 min | 3 min (after 07:00) | yes | yes | on next natural wake |
| Daytime | 10:00–20:00 | Gallery | 60 min | 3 min | yes (5-min cooldown) | yes | on next natural wake |
| Evening (Sonos off) | 20:00–22:00 | Gallery | 60 min | disabled | yes | yes | on next natural wake |
| Night (Sonos off) | 22:00–00:00 | Night | 60 min | disabled | yes | yes | on next natural wake |
| Quiet hours | 00:00–05:00 | Night | 60 min | disabled | **disabled** | yes | on next natural wake |
| Pre-dawn | 05:00–06:30 | Night | 60 min | disabled | yes | yes | on next natural wake |
| Now-Playing (within Sonos hours) | variable | Now-Playing | 15 min (minute-tick disabled; track changes come via HA wake-reason) | — (mode itself) | yes | yes | immediate (device is already awake during fast-path polls) |

Configurable parameters with defaults:

- `sonos_active_start` — default `07:00`. Before this time the Sonos fast-path timer is not armed.
- `sonos_active_end` — default `20:00`. After this time the Sonos fast-path timer is not armed.
- `quiet_start` — default `00:00`. PIR disarmed starting at this time.
- `quiet_end` — default `05:00`. PIR re-armed at this time.
- `fast_path_interval` — default `180` seconds.
- Per-mode timer durations.

All parameters SHALL be editable via `config.h` or, where appropriate for runtime tuning (Sonos hours, quiet hours), via HA input helpers read over MQTT on wake.

Strategy notes:

- **Timer cadence** is the mode's own refresh cycle, used for minute-ticks and data freshness within the active mode.
- **Sonos fast-path timer** is an additional, independent wake that runs during Sonos-eligible hours (default 07:00–20:00, configurable). On each fast-path wake, the device reads the retained MQTT `active_mode` topic and, if it has changed to `now-playing` since the last drawn mode, fetches the Now-Playing PNG. This bounds the activation latency for Now-Playing to the fast-path interval (default 3 minutes) during Sonos hours. Outside Sonos hours, activation latency falls back to the mode's own timer cadence, because nobody expects the kitchen dashboard to react to music at 02:00. If no change is detected on a fast-path wake, the device returns to sleep immediately without fetching the renderer.
- **PIR disabled during quiet hours** (00:00–05:00) preserves battery during sleep time and ensures Night mode stays active when someone briefly passes through the kitchen at night.
- **IMU INT always armed** — a deliberate double-tap at 03:00 to cycle through modes SHALL still work.
- **On each wake** (regardless of source), the device queries HA's retained MQTT `active_mode` before fetching. If the active mode differs from the last drawn mode, a full refresh is performed; otherwise the device applies partial-refresh rules or returns to sleep unchanged.

#### Scenario: Morning sequence

- **WHEN** the device is in Summary mode at 08:45 with the last wake at 08:30 (15-min timer)
- **THEN** the next timer wake fires at 08:45, the device reads retained MQTT (still `summary`), fetches `/display/summary.png`, performs partial-refresh for the clock region, and returns to deep sleep with the 15-min timer + 3-min Sonos fast-path both armed

#### Scenario: Sonos fast-path activation during Gallery

- **WHEN** it is 14:17 (within Sonos hours 07:00–20:00), the device is in Gallery mode (60-min timer, last wake at 14:00), and Sonos starts playing at 14:18
- **THEN** the 3-min Sonos fast-path wake fires at 14:20 (at most), the device reads retained MQTT now showing `now-playing`, fetches `/display/now-playing.png`, performs a full refresh, sets last-drawn mode to `now-playing`, and returns to sleep with the Now-Playing mode's own 15-min timer + 3-min fast-path both armed

#### Scenario: Sonos plays outside the fast-path window

- **WHEN** it is 21:30 (outside the default Sonos window 07:00–20:00) and Sonos starts playing
- **THEN** the Sonos fast-path timer is not armed; the device will observe the new `now-playing` state only on its next natural wake (mode timer, PIR, or IMU); activation latency can be up to the mode's timer cadence

#### Scenario: Operator adjusts Sonos hours

- **WHEN** the operator changes `sonos_active_end` from `20:00` to `22:00` via HA helper and the device's next wake reads the updated value
- **THEN** subsequent sleep cycles between 20:00 and 22:00 arm the fast-path timer, and Now-Playing responsiveness in that window drops to the 3-minute bound

#### Scenario: Quiet-hours discipline

- **WHEN** the device is in Night mode at 02:30 and someone walks through the kitchen
- **THEN** the PIR does NOT wake the device (PIR disarmed during quiet hours), and the device continues the 60-min timer cadence

#### Scenario: Track change during Now-Playing

- **WHEN** the device is awake in Now-Playing mode (15-min timer), HA publishes a `wake_reason: track_change` signal, and the device reads it within the same wake cycle
- **THEN** the device re-fetches `/display/now-playing.png` before re-entering deep sleep, so the fresh album art is visible

#### Scenario: Cold boot

- **WHEN** the device cold-boots (power restored, or battery depleted and then charged)
- **THEN** the device connects to WiFi and MQTT, reads retained `active_mode`, fetches the corresponding PNG, performs a full refresh, publishes device state (including `wake_reason: cold_boot`), and arms the mode's timer + fast-path before entering deep sleep

#### Scenario: Boot after OTA

- **WHEN** the device reboots after a successful OTA update
- **THEN** the device follows the cold-boot flow, additionally publishes the new build version to `inkplate/state/device`, and HA may log or notify the operator

### Requirement: Wake sources

The device SHALL arm the following wake sources on each deep-sleep entry:

- **Timer wake** — configurable per mode. Summary/Weather: 15 minutes. Gallery: 60 minutes. Night: 60 minutes (or 1 minute if minute-tick is enabled). Now-Playing: wake only via HA signal, not timer.
- **PIR wake** — GPIO configured as wake-capable. Debounced so brief passes don't wake repeatedly. 5-minute cooldown between PIR-triggered wakes.
- **LSM6DSO tap wake** — configured with hardware tap-detect + `LATCHED_INT`. Without INT1 wired to an ESP32 GPIO the firmware polls `TAP_SRC` on every Timer wake; a pending tap upgrades the wake reason to IMU. Worst-case activation latency is one timer period.
- **HA wake** — the mechanism defined by `device-wake-protocol` (MQTT or HTTP).

Disarming unused wake sources SHALL occur when a mode doesn't need them (e.g., PIR wake is disabled during quiet-hours if the operator configures it so).

#### Scenario: PIR triggered within cooldown

- **WHEN** PIR triggers a wake at time T, and triggers again at T + 2 minutes
- **THEN** the second trigger does NOT wake the device (5-minute cooldown)

#### Scenario: Gallery hours, no minute tick

- **WHEN** the device enters deep sleep in Gallery mode
- **THEN** the only armed wake sources are the 60-minute timer and IMU INT (latched-tap polling picks up gestures on the next timer wake); HA-driven wakes arrive as MQTT messages observed on each natural wake

### Requirement: Active-mode discovery

On each wake, the device SHALL query HA's active-mode endpoint before fetching any PNG. The endpoint returns the currently-active mode name (one of the six: `summary`, `weather`, `gallery`, `night`, `now-playing`, or potentially `gallery_text` if the renderer exposes per-flavor endpoints — implementation detail).

The device SHALL NOT hard-code the schedule. Schedule logic lives in HA; the device trusts HA's answer.

#### Scenario: HA reports gallery

- **WHEN** the device wakes at 14:00 and queries HA
- **THEN** HA returns `gallery`, and the device fetches `/display/gallery.png`

#### Scenario: HA reports now-playing

- **WHEN** the device wakes after receiving an HA wake signal, queries HA, and HA returns `now-playing`
- **THEN** the device fetches `/display/now-playing.png`

### Requirement: Tap detection

The LSM6DSO IMU SHALL be configured to generate hardware tap and double-tap interrupts on its INT1 pin. The device firmware SHALL:

- Treat a **single tap** as a request to activate Weather peek for 5 minutes, then auto-revert. Report the tap to HA so HA's override-state updates.
- Treat a **double tap** as a request to toggle the Summary/Gallery mode for the current scheduled window. Report to HA.

#### Scenario: Single tap during Summary hours

- **WHEN** a single tap occurs at 09:00
- **THEN** the device reports the tap to HA, HA activates Weather peek, HA signals wake, the device fetches Weather PNG

#### Scenario: Double tap

- **WHEN** a double tap occurs during Gallery hours
- **THEN** the device reports to HA, HA toggles to Summary (persistent until next scheduled transition), HA signals wake, the device fetches Summary

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

When the renderer is unreachable (timeout, connection refused, 5xx):

- The device SHALL NOT blank the display; the last rendered face remains visible.
- A tiny corner indicator (e.g., a small circle in the battery area, 6u square) SHALL appear during the failure state.
- The device SHALL retry with back-off: 30s, 1min, 5min, 15min, 30min, capped at 30min.
- Once reachability is restored, the indicator is cleared on the next render.

Similarly, when HA's active-mode endpoint is unreachable:

- The device SHALL fall back to a mode determined by the current local time per the schedule (06:30–10:00 Summary, 10:00–22:00 Gallery, 22:00–06:30 Night).
- The fall-back indicator is visually identical to the renderer-failure indicator.

#### Scenario: Renderer briefly unreachable

- **WHEN** a fetch fails with a connection timeout at 14:30
- **THEN** the current face remains visible, the tiny indicator appears, the device retries after 30s

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
