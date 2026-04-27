## MODIFIED Requirements

### Requirement: Wake sources

The device SHALL arm the following wake sources on each deep-sleep entry:

- **Timer wake** — configurable per mode. Summary/Weather: 15 minutes. Gallery: 60 minutes. Night: 60 minutes (or 1 minute if minute-tick is enabled). Now-Playing: wake only via HA signal or timer per the sleep-strategy table, not directly user-triggered.
- **LSM6DSO INT wake** — GPIO connected to the IMU's INT1 pin, configured with hardware tap-detect enabled in the IMU's INT registers.
- **HA wake** — the mechanism defined by `device-wake-protocol` (MQTT retained active_mode + `inkplate/command/wake` pulse). HA-initiated wakes subsume what was previously the on-device PIR path: the IKEA motion sensor (via `ha-integrations`) publishes to the wake topic, which the device observes on its next natural wake.

Disarming unused wake sources SHALL occur when a mode doesn't need them.

The device SHALL NOT arm a dedicated PIR wake source. Motion detection lives in HA.

#### Scenario: Gallery hours wake arming

- **WHEN** the device enters deep sleep in Gallery mode during daytime (10:00–20:00)
- **THEN** the only armed wake sources are the 60-minute timer, the 3-minute Sonos fast-path timer, IMU INT (subject to the door filter), and HA wake via the retained active_mode topic

#### Scenario: Motion observed via HA

- **WHEN** the IKEA kitchen motion sensor fires during Summary hours and HA publishes `inkplate/command/wake`
- **THEN** the device's next natural wake (timer or fast-path) observes the retained `active_mode` and refreshes accordingly; the device does NOT wake directly from motion

### Requirement: Sleep strategy

The firmware SHALL follow a unified sleep-and-wake strategy that coordinates timer cadence, armed wake sources, and fast-path responsiveness across modes and time-of-day. The policy is defined by the following table; any future changes to timers or wake sources SHALL update this table.

| Period | Hours (default) | Mode | Timer cadence | Sonos fast-path timer | IMU INT armed | HA wake on MQTT observed |
|---|---|---|---|---|---|---|
| Morning | 06:30–10:00 | Summary | 15 min | 3 min (after 07:00) | yes | on next natural wake |
| Daytime | 10:00–20:00 | Gallery | 60 min | 3 min | yes | on next natural wake |
| Evening (Sonos off) | 20:00–22:00 | Gallery | 60 min | disabled | yes | on next natural wake |
| Night (Sonos off) | 22:00–00:00 | Night | 60 min | disabled | yes | on next natural wake |
| Quiet hours | 00:00–05:00 | Night | 60 min | disabled | yes | on next natural wake |
| Pre-dawn | 05:00–06:30 | Night | 60 min | disabled | yes | on next natural wake |
| Now-Playing (within Sonos hours) | variable | Now-Playing | 15 min | — (mode itself) | yes | immediate (device is already awake during fast-path polls) |

Configurable parameters with defaults:

- `sonos_active_start` — default `07:00`. Before this time the Sonos fast-path timer is not armed.
- `sonos_active_end` — default `20:00`. After this time the Sonos fast-path timer is not armed.
- `quiet_start` — default `00:00`. Used by HA to gate motion-driven wake pulses (not by the device directly).
- `quiet_end` — default `05:00`.
- `fast_path_interval` — default `180` seconds.
- Per-mode timer durations.

All parameters SHALL be editable via `config.h` or, where appropriate for runtime tuning (Sonos hours, quiet hours), via HA input helpers read over MQTT on wake.

Strategy notes:

- **Timer cadence** is the mode's own refresh cycle, used for minute-ticks and data freshness within the active mode.
- **Sonos fast-path timer** — unchanged from prior version. On each fast-path wake, the device reads the retained MQTT `active_mode` topic and acts only if it has changed.
- **IMU INT always armed** — a deliberate double-tap at 03:00 to cycle through modes SHALL still work. The gyroscope door filter suppresses false positives from late-night fridge use.
- **Motion-triggered wake via HA** — the IKEA motion sensor is HA's concern; the device does not own motion hardware. Motion-wake latency is bounded by the timer/fast-path cadence of the current period.
- **On each wake** (regardless of source), the device queries HA's retained MQTT `active_mode` before fetching.

#### Scenario: Morning sequence

- **WHEN** the device is in Summary mode at 08:45 with the last wake at 08:30 (15-min timer)
- **THEN** the next timer wake fires at 08:45, the device reads retained MQTT (still `summary`), fetches `/display/summary.png`, performs partial-refresh for the clock region, and returns to deep sleep with the 15-min timer + 3-min Sonos fast-path both armed

#### Scenario: Sonos fast-path activation during Gallery

- **WHEN** it is 14:17 (within Sonos hours 07:00–20:00), the device is in Gallery mode (60-min timer, last wake at 14:00), and Sonos starts playing at 14:18
- **THEN** the 3-min Sonos fast-path wake fires at 14:20 (at most), the device reads retained MQTT now showing `now-playing`, fetches `/display/now-playing.png`, performs a full refresh, sets last-drawn mode to `now-playing`, and returns to sleep with the Now-Playing mode's own 15-min timer + 3-min fast-path both armed

#### Scenario: Motion during Gallery hours

- **WHEN** the IKEA kitchen motion sensor fires at 15:30, HA pulses `inkplate/command/wake`, the device is currently in deep sleep in Gallery mode
- **THEN** the device observes the wake pulse on its next natural wake — either the 3-min Sonos fast-path (latency ≤ 3 min during Sonos hours) or the 60-min Gallery timer — and refreshes if `active_mode` has changed

#### Scenario: Cold boot

- **WHEN** the device cold-boots (power restored, or battery depleted and then charged)
- **THEN** the device connects to WiFi and MQTT, reads retained `active_mode`, fetches the corresponding PNG, performs a full refresh, publishes device state (including `wake_reason: cold_boot`), and arms the mode's timer + fast-path before entering deep sleep

#### Scenario: Boot after OTA

- **WHEN** the device reboots after a successful OTA update
- **THEN** the device follows the cold-boot flow, additionally publishes the new build version to `inkplate/state/device`, and HA may log or notify the operator

## REMOVED Requirements

### Requirement: PIR wake source and cooldown

**Reason**: Motion detection relocated to HA (IKEA Zigbee/Matter motion sensor). The device no longer arms a PIR wake source, no longer enforces a 5-minute cooldown in RTC memory, and no longer disarms a PIR during quiet hours. The equivalent behavior lives in `ha-integrations`' Motion-wake requirement: HA's automation applies the 5-minute throttle and the quiet-hours condition before publishing `inkplate/command/wake`.

**Migration**: the `Reason::PIR` enum entry is deleted from `firmware/include/wake.h` (see companion deletion in `device-wake-protocol`). The `last_pir_wake_epoch` field is removed from `wake::persisted()`. The `kPirCooldownSec` constant is removed from `config.h`. Test scenarios asserting PIR behavior are deleted along with the `MockPir` harness.
