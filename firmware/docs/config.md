# Configuration parameters

All tunables live in `firmware/include/config.h`. **The schedule planner
(`firmware/src/wake.cpp`) is the actual source of truth for wake cadence**;
the per-mode timers below are fallback values used when the planner doesn't
apply (cold boot, HACommand, etc.). When in doubt, read `wake.cpp:tierFor()`.

## Mode timers

These are the legacy fallback timers — kept for cold-boot and the rare paths
that bypass the schedule planner. The actual minute-by-minute cadence is
decided by `wake::planWake()` per-tier (see `firmware/README.md` and
`firmware/docs/wake-protocol.md`).

| Parameter | Default | Notes |
| --------- | ------- | ----- |
| `kSummaryTimerSec`  | **60**  | Daytime cadence; the schedule planner overrides this with 15-min Full + 1-min Partial during Morning. |
| `kWeatherTimerSec`  | **60**  | Same — overridden by the planner during alternation slots. |
| `kGalleryTimerSec`  | **60**  | Same — overridden by Midday's 30-min Full + 5-min PollPartial cadence. |
| `kNightTimerSec`    | **900** | 15-min cadence; matches the Night tier's Full-only schedule. |
| `kSonosFastPathSec` | **60**  | Now-Playing forces 1-min Full; this fallback aligns with that. Redundant in normal operation but retained for non-planner paths. |

The 60 s daytime fallback exists so that any path bypassing the schedule
planner still wakes within a minute — important for HA-driven `wake` MQTT
pulses landing on a sleeping device's next wakeup window.

## Ghost cadence

| Parameter | Default | Notes |
| --------- | ------- | ----- |
| `kGhostClearPartialCount` | 30 | Legacy: force a full refresh after this many partials. Currently dormant — the post-Full zone cleanup (`main_loop.cpp:doFull` epilogue) and the seed-then-draw partial path together handle ghost-clearing without a global counter, but the constant remains in case ghosting reappears in a new configuration. |

## LSM6DSO tap

| Parameter | Default | Notes |
| --------- | ------- | ----- |
| `kTapThreshold` | **1** | LSM6DSO tap threshold in 1/32 g (≈62.5 mg). Lowered from 12 → 1 for the wire-tied frame mount, where mechanical coupling damps shock arrival at the IMU. Cannot go lower. |
| `kTapDurationMs` | 40 | LSM6DSO shock-duration cap. |
| `kDoubleTapWindowMs` | 350 | Inter-tap window for double-tap latching. The frame's natural ring period sits comfortably inside this window, which is why a single firm tap usually latches `DOUBLE`. |
| `kGestureGraceMs` | 2000 | After publishing a gesture, the firmware subscribes to `active_mode` for up to this many milliseconds to pick up HA's response before fetching. Almost always satisfied within ~300 ms; the upper bound is a safety net. |

## Time-of-day windows

| Parameter | Default | Notes |
| --------- | ------- | ----- |
| `kQuietStartHour` | 0 | Operator-side reference only; the device no longer gates anything on quiet hours (PIR moved to HA, gestures pass through to HA which honors quiet hours upstream). |
| `kQuietEndHour` | 5 | Same. |
| `kSonosStartHour` | 7 | Sonos fast-path arming window start. |
| `kSonosEndHour` | 20 | Sonos fast-path arming window end. |

## Network

| Parameter | Default | Notes |
| --------- | ------- | ----- |
| `kWifiConnectTimeoutMs` | 10000 | WiFi association timeout. |
| `kHttpTimeoutMs` | 3000 | Per-request HTTP timeout. |
| `kRendererMaxRetries` | 3 | Fetch retries before drawing the unavailable corner indicator. |
| `kRendererBackoffSec` | `{2, 8, 30}` | Backoff ladder between retries. |

## MQTT topics

| Constant | Topic |
| -------- | ----- |
| `kTopicActiveMode` | `inkplate/command/active_mode` |
| `kTopicWake`       | `inkplate/command/wake` |
| `kTopicGesture`    | `inkplate/state/gesture` |
| `kTopicDeviceState` | `inkplate/state/device` |

## Schedule planner constants (`firmware/src/wake.cpp`)

These aren't in `config.h` — they're inline constants in the planner — but
they're the values that actually control the wake cadence.

| Tier | Boundary (local) | full_min | poll_min | partial_min | partial_brings_poll |
| --- | --- | --- | --- | --- | --- |
| Night | 22:00 – 06:30 | 15 | — | — | — |
| Morning | 06:30 – 10:00 | 15 | 3 | 1 | false |
| Midday | 10:00 – 17:00 | 30 | — | 5 | true (PollPartial) |
| Evening | 17:00 – 22:00 | 15 | 3 | 1 | false |

To change the schedule, edit `tierFor()` in `wake.cpp`, update
`firmware/test/scenarios/schedule_tests.cpp` to cover the new boundaries,
and (importantly) keep the equivalent ranges in
`ha/automations/schedule.yaml` aligned. See `HOWTO.md § Customize the
schedule` for the full procedure.
