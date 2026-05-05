#pragma once

#include "hal/HAL.h"
#include "wake.h"

namespace fw {

// Single firmware tick. Invoked once per wake:
//   1. identify wake reason
//   2. connect WiFi + MQTT
//   3. resolve the active mode (MQTT retained, then time-of-day fallback)
//   4. fetch PNG + drawImage (full/partial refresh per rules)
//   5. publish device state + any gesture
//   6. arm wake sources and return; caller enters deep sleep
//
// Host tests call this directly via Scenario. On-device, `main.cpp`'s
// `setup()` calls it and then invokes `IClock::sleepFor`.
void tick(hal::HAL hal, wake::Reason reason);

// Build version string baked into device-state publishes. Bump on every
// shipped firmware change so HA's `inkplate_device_build` sensor and the
// post-wedge diagnostic correlate to a real commit.
constexpr const char* kBuildVersion = "0.8.1-active-mode-fallback";

}  // namespace fw
