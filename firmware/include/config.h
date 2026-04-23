#pragma once

#include <cstdint>

// All tunable parameters live here. Runtime overrides arrive via HA MQTT
// helpers on each wake; these are fallback defaults when HA is unreachable.

namespace fw::config {

// Per-mode timer cadence (seconds). All modes poll at 60 s for responsiveness
// (motion → wake pulse, Sonos activation, scheduled transitions all caught
// within a minute). The per-mode constants stay as named values so individual
// modes can diverge later (e.g., if Gallery proves OK on a slower tick).
// Battery cost: roughly 5× the previous design; operator monitors and tunes.
constexpr int kSummaryTimerSec    = 60;
constexpr int kWeatherTimerSec    = 60;
constexpr int kGalleryTimerSec    = 60;
constexpr int kNightTimerSec      = 60;
constexpr int kSonosFastPathSec   = 60;   // redundant with mode timers now

// Ghost-clear: after N partial refreshes within a mode, force a full refresh.
constexpr int kGhostClearPartialCount = 30;

// LSM6DSO tap thresholds (driver units, device-dependent; re-calibrate with
// hardware). These are placeholder values.
constexpr int kTapThreshold   = 12;
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
inline constexpr const char* kTopicActiveMode  = "inkplate/command/active_mode";
inline constexpr const char* kTopicWake        = "inkplate/command/wake";
inline constexpr const char* kTopicGesture     = "inkplate/state/gesture";
inline constexpr const char* kTopicDeviceState = "inkplate/state/device";

}  // namespace fw::config
