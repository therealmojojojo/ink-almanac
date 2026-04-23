#pragma once

#include <cstdint>

#include "hal/types.h"

namespace hal {

// IIMU — LSM6DSO-style 6-DoF IMU abstraction.
//
// Contract:
//   * `init()` is idempotent. Safe to call multiple times.
//   * `configureTap(threshold, durationMs)` sets the single-tap INT threshold
//     (hardware units, calibrated in firmware) and minimum duration.
//   * `configureDoubleTap(windowMs)` enables double-tap detection with the
//     given inter-tap window (ms).
//
// Lifecycle:
//   `init()` must be called before any configure/read; implementations
//   that need I²C bring-up handle it there.
class IIMU {
 public:
  virtual ~IIMU() = default;
  virtual void init() = 0;
  virtual void configureTap(int threshold, int durationMs) = 0;
  virtual void configureDoubleTap(int windowMs) = 0;

  // Consume a latched tap event, if any. Returns true when a tap was pending
  // and clears the latch; sets `*is_double` to true for a double-tap, false
  // for a single-tap. Without INT1 wired to an ESP32 GPIO this is the only
  // path taps reach the firmware — LSM6DSO's LATCHED_INT bit keeps the event
  // visible across deep sleep until it's read.
  virtual bool drainPendingTap(bool* is_double) = 0;
};

}  // namespace hal
