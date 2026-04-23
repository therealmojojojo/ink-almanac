#include "hal/mock/MockBattery.h"

#include <algorithm>

#include "hal/mock/MockClock.h"

namespace sim {

MockBattery::MockBattery(MockClock& clock, int initial_percentage)
    : clock_(clock),
      consumed_mah_(static_cast<float>(100 - initial_percentage) *
                    capacity_mah_ / 100.0f) {
  (void)clock_;
}

float MockBattery::readVoltage() {
  // Linear stand-in from 3.0 V (empty) to 4.2 V (full).
  int pct = readPercentage();
  return 3.0f + (static_cast<float>(pct) / 100.0f) * 1.2f;
}

int MockBattery::readPercentage() {
  float remaining = std::max(0.0f, capacity_mah_ - consumed_mah_);
  int pct = static_cast<int>((remaining / capacity_mah_) * 100.0f);
  return std::clamp(pct, 0, 100);
}

void MockBattery::reset(int percentage) {
  consumed_mah_ =
      static_cast<float>(100 - percentage) * capacity_mah_ / 100.0f;
  per_source_mah_.clear();
  source_ = "idle";
}

void MockBattery::setCurrentMa(const std::string& source, float mA) {
  current_ma_[source] = mA;
}

void MockBattery::onTick(int seconds, bool asleep) {
  if (seconds <= 0) return;
  float mA;
  if (asleep) {
    auto it = current_ma_.find("deep_sleep");
    mA = it == current_ma_.end() ? default_ma_ : it->second;
  } else {
    auto it = current_ma_.find(source_);
    mA = it == current_ma_.end() ? default_ma_ : it->second;
  }
  // mAh accumulated = mA * hours = mA * seconds / 3600
  const float delta = mA * static_cast<float>(seconds) / 3600.0f;
  consumed_mah_ += delta;
  per_source_mah_[asleep ? "deep_sleep" : source_] += delta;
}

}  // namespace sim
