# Configuration parameters

All tunables live in `firmware/include/config.h`. Runtime overrides arrive via
HA MQTT helpers on each wake; values here are fallback defaults when HA is
unreachable.

## Mode timers

| Parameter | Default | Notes |
| --------- | ------- | ----- |
| `kSummaryTimerSec` | 900 | 15-minute refresh; during Summary hours (06–10 local) |
| `kWeatherTimerSec` | 900 | 15-minute refresh; during Weather hours |
| `kGalleryTimerSec` | 3600 | 60-minute; Gallery / delight content rarely changes mid-hour |
| `kNightTimerSec`   | 3600 | 60-minute; Night mode is low-activity |
| `kSonosFastPathSec` | 180 | 3-minute poll during Sonos-eligible hours |

## Ghost cadence

| Parameter | Default | Notes |
| --------- | ------- | ----- |
| `kGhostClearPartialCount` | 30 | Force a full refresh after this many partials |

## LSM6DSO tap

| Parameter | Default | Notes |
| --------- | ------- | ----- |
| `kTapThreshold` | 12 | Driver-units; recalibrate with real hardware |
| `kTapDurationMs` | 40 | Minimum tap duration |
| `kDoubleTapWindowMs` | 350 | Inter-tap window for double-tap |

## Time-of-day windows

| Parameter | Default | Notes |
| --------- | ------- | ----- |
| `kQuietStartHour` | 0 | Quiet window start (HA reads this when gating motion-triggered wakes; the device no longer uses it since PIR moved to HA) |
| `kQuietEndHour` | 5 | Quiet window end |
| `kSonosStartHour` | 7 | Sonos fast-path timer armed only within this window |
| `kSonosEndHour` | 20 | |

## Network

| Parameter | Default | Notes |
| --------- | ------- | ----- |
| `kWifiConnectTimeoutMs` | 10000 | WiFi association timeout |
| `kHttpTimeoutMs` | 3000 | Per-request HTTP timeout |
| `kRendererMaxRetries` | 3 | Fetch retries before surfacing the unavailable indicator |
| `kRendererBackoffSec` | `{2, 8, 30}` | Backoff ladder |

## MQTT topics

| Constant | Topic |
| -------- | ----- |
| `kTopicActiveMode` | `inkplate/command/active_mode` |
| `kTopicWake`       | `inkplate/command/wake` |
| `kTopicGesture`    | `inkplate/state/gesture` |
| `kTopicDeviceState` | `inkplate/state/device` |
