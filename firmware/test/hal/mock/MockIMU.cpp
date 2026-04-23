#include "hal/mock/MockIMU.h"

#include "hal/mock/MockClock.h"

namespace sim {

MockIMU::MockIMU(MockClock& clock) : clock_(clock) {}

void MockIMU::configureTap(int threshold, int durationMs) {
  tap_threshold_ = threshold;
  tap_duration_ms_ = durationMs;
}

void MockIMU::configureDoubleTap(int windowMs) {
  double_tap_window_ms_ = windowMs;
}

void MockIMU::scriptTap(hal::Epoch at, bool isDouble) {
  pending_taps_.push_back({at, isDouble});
}

bool MockIMU::drainTap(hal::Epoch up_to, TapEvent* out) {
  if (pending_taps_.empty()) return false;
  if (pending_taps_.front().at_epoch > up_to) return false;
  *out = pending_taps_.front();
  pending_taps_.pop_front();
  return true;
}

bool MockIMU::drainPendingTap(bool* is_double) {
  TapEvent ev{};
  if (!drainTap(clock_.nowEpoch(), &ev)) return false;
  if (is_double) *is_double = ev.isDouble;
  return true;
}

}  // namespace sim
