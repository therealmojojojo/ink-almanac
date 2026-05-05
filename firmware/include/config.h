#pragma once

#include <cstdint>

// All tunable parameters live here. Runtime overrides arrive via HA MQTT
// helpers on each wake; these are fallback defaults when HA is unreachable.

namespace fw::config {

// Per-mode timer cadence (seconds). Daytime modes poll at 60 s for
// responsiveness (motion → wake pulse, Sonos activation, scheduled
// transitions all caught within a minute). Night sleeps 15× longer
// because content doesn't change overnight (no Sonos, no breaking
// news, no schedule transitions until 06:00) and the slower cadence
// dramatically extends battery life — at 60 s every night would cost
// 480 wakes between 22:00 and 06:00; at 900 s it's 32. Tap wakes via
// ext0 still work normally at night.
constexpr int kSummaryTimerSec    = 60;
constexpr int kWeatherTimerSec    = 60;
constexpr int kGalleryTimerSec    = 60;
constexpr int kNightTimerSec      = 900;  // 15 min — see above
constexpr int kSonosFastPathSec   = 60;   // redundant with daytime mode timers

// Ghost-clear: after N partial refreshes within a mode, force a full refresh.
constexpr int kGhostClearPartialCount = 30;

// LSM6DSO INT1 is soldered onto the SW3 wake-button net (GPIO 36, with
// R41 pull-up to 3V3). Both events arrive as `ext0` LOW; the firmware
// disambiguates by reading WAKE_UP_SRC after wake. See gestures.md.
constexpr int kImuWakeGpio = 36;

// LSM6DSO tap thresholds (driver units; 1 LSB ≈ 62.5 mg at ±2 g full-scale).
// Tuned to require a deliberate finger tap and reject incidental motion:
//
//   * 1 LSB ≈ 0.0625 g — the chip's minimum. Tuned for a frame mount
//     where the LSM6DSO breakout is wire-tied to the Inkplate (not
//     glued to the frame back), so taps reach the chip via glass →
//     mat → PCB → wire-tie. That path absorbs most of the impact,
//     making the lowest threshold the only one that registers natural
//     taps. The SLOPE_FDS HPF still rejects static gravity and slow
//     rotations; the spurious-wake guard in tick() catches false ext0
//     fires that don't latch SINGLE_TAP/DOUBLE_TAP bits, bounding the
//     cost of a low threshold. On a wall mount the ambient-event rate
//     is much lower than on a fridge, so threshold = 1 is viable; if
//     phantom wakes appear in real use, raise to 4–6.
//   * Combined with the existing Z-axis-only TAP_CFG0 (=0x0F) and the
//     spurious-wake guard in tick() (re-sleep on TAP_SRC=0x00), the
//     wake-on-tap path triggers only on intentional impact along the
//     fridge-perpendicular axis.
//
// Implementation notes for the real driver (not exposed via IIMU):
//   * INT1 must be configured open-drain active-low (CTRL3_C: PP_OD=1,
//     H_LACTIVE=1) so it can share the wake-button net without fighting
//     R41 or the switch.
//   * Pulsed (not latched on INT1, but TAP_SRC IS latched via TAP_CFG0
//     LIR=11) — line returns to high-Z after the SHOCK window so the
//     pull-up restores idle HIGH for the next event.
//   * Z axis only (TAP_CFG0 bits: TAP_X_EN=0, TAP_Y_EN=0, TAP_Z_EN=1) —
//     rejects lateral shocks from fridge-door slams.
constexpr int kTapThreshold   = 1;
constexpr int kTapDurationMs  = 40;
constexpr int kDoubleTapWindowMs = 350;

// Gesture-handler grace window. On an IMU wake, after publishing the gesture
// to state/gesture, the firmware subscribes to active_mode for up to this
// many milliseconds to pick up HA's post-gesture decision before committing
// to the fetch. If HA doesn't respond in-window the device proceeds with the
// pre-gesture retained value; the tap-triggered face change then lands on the
// next natural wake. 2000 ms matches the spec default in add-local-clock-tick
// "Tap detection".
constexpr int kGestureGraceMs = 2000;

// Local-time offset from UTC, in seconds. Applied to `clock.nowEpoch()`
// before computing minute-of-day for the wake-schedule planner and
// hour-of-day for the legacy quiet-hours check.
//
// Hardcoded for Europe/Bucharest summer (UTC+3). This will read wrong by
// 1 h between roughly late October and late March each year, in which case
// schedule tier boundaries (22:00 / 06:30 / 10:00 / 17:00) shift by an hour
// — acceptable until we wire NTP + a tz-aware library on device.
constexpr int kTzOffsetSec = 3 * 3600;

// Time-of-day windows (local-hour ints, 0–23).
constexpr int kQuietStartHour  = 0;
constexpr int kQuietEndHour    = 5;
constexpr int kSonosStartHour  = 7;
constexpr int kSonosEndHour    = 20;

// Network
constexpr int kWifiConnectTimeoutMs = 10000;
constexpr int kHttpTimeoutMs        = 3000;
constexpr int kRendererMaxRetries   = 3;
constexpr int kRendererBackoffSec[] = {2, 8, 30};

// MQTT topics
inline constexpr const char* kTopicActiveMode      = "inkplate/command/active_mode";
inline constexpr const char* kTopicSchedule        = "inkplate/command/schedule";
inline constexpr const char* kTopicWake            = "inkplate/command/wake";
inline constexpr const char* kTopicGesture         = "inkplate/state/gesture";
inline constexpr const char* kTopicDeviceState     = "inkplate/state/device";
inline constexpr const char* kTopicNowPlayingTrack = "inkplate/state/now_playing_track";
inline constexpr const char* kTopicActiveOverride  = "inkplate/state/active_override";

}  // namespace fw::config
