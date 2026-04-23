#pragma once

#include <deque>

#include "hal/IIMU.h"
#include "hal/types.h"

namespace sim {

class MockClock;

class MockIMU : public hal::IIMU {
 public:
  explicit MockIMU(MockClock& clock);

  void init() override { inited_ = true; }
  void configureTap(int threshold, int durationMs) override;
  void configureDoubleTap(int windowMs) override;
  bool drainPendingTap(bool* is_double) override;

  // Test-facing API
  struct TapEvent {
    hal::Epoch at_epoch;
    bool isDouble;
  };
  void scriptTap(hal::Epoch at, bool isDouble = false);

  // Returns the next pending tap at-or-before the given time. Consumes it.
  // Returns nullopt if no tap is pending.
  bool drainTap(hal::Epoch up_to, TapEvent* out);

  bool inited() const { return inited_; }
  int tapThreshold() const { return tap_threshold_; }
  int tapDurationMs() const { return tap_duration_ms_; }
  int doubleTapWindowMs() const { return double_tap_window_ms_; }

 private:
  MockClock& clock_;
  bool inited_ = false;
  int tap_threshold_ = 0;
  int tap_duration_ms_ = 0;
  int double_tap_window_ms_ = 0;
  std::deque<TapEvent> pending_taps_;
};

}  // namespace sim
