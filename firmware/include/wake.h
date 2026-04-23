#pragma once

#include <cstdint>

#include "hal/types.h"
#include "modes.h"

namespace fw::wake {

// Wake reasons. `pir` removed — motion now lives in HA (see
// openspec/changes/move-pir-to-ha-motion/); HA-driven wakes arrive as
// `HACommand`.
enum class Reason {
  ColdBoot,
  Timer,
  IMU,
  HACommand,
  SonosFastPath,
  PostOTA,
};

constexpr const char* toString(Reason r) {
  switch (r) {
    case Reason::ColdBoot:       return "cold_boot";
    case Reason::Timer:          return "timer";
    case Reason::IMU:             return "imu";
    case Reason::HACommand:       return "ha_command";
    case Reason::SonosFastPath:   return "sonos_fast_path";
    case Reason::PostOTA:         return "post_ota";
  }
  return "unknown";
}

// Persisted across deep sleeps (RTC_SLOW memory on ESP32; ordinary globals on host).
struct Persisted {
  fw::modes::Mode current_mode = fw::modes::Mode::Unknown;
  int partial_refresh_count = 0;
};

Persisted& persisted();

// Host-test only: reset persisted state between scenarios.
void reset();

// Decide which wake sources to arm before the next sleep, based on the mode
// that will be resumed and the current wall-clock hour.
hal::WakeSourceMask armMask(fw::modes::Mode next_mode, int hour);

}  // namespace fw::wake
