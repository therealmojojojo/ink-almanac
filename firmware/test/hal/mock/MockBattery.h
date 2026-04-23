#pragma once

#include <string>
#include <unordered_map>

#include "hal/IBattery.h"

namespace sim {

class MockClock;

// MockBattery — consumes accumulated wake-time-by-source and reports a
// voltage curve. Sources are identified by string keys (e.g. "deep_sleep",
// "active_summary", "active_now_playing", "wifi_connect"). Firmware tags the
// current wake category via `setSource()` before a simulated tick.
class MockBattery : public hal::IBattery {
 public:
  explicit MockBattery(MockClock& clock, int initial_percentage = 100);

  float readVoltage() override;
  int readPercentage() override;

  // Reset state to the given percentage and clear per-source accounting.
  void reset(int percentage);

  // Configure per-source current draw (mA). Sources not in the map
  // default to `default_ma_`.
  void setCurrentMa(const std::string& source, float mA);
  void setDefaultMa(float mA) { default_ma_ = mA; }

  // Firmware sets this before any tick so that accumulated time is
  // attributed correctly.
  void setSource(std::string source) { source_ = std::move(source); }

  // Hook called by MockClock's tick callback.
  void onTick(int seconds, bool asleep);

  // Reporting
  float totalConsumedMah() const { return consumed_mah_; }
  float capacityMah() const { return capacity_mah_; }
  const std::unordered_map<std::string, float>& perSourceMah() const {
    return per_source_mah_;
  }

 private:
  MockClock& clock_;
  std::unordered_map<std::string, float> current_ma_;
  std::unordered_map<std::string, float> per_source_mah_;
  std::string source_ = "idle";
  float default_ma_ = 0.05f;            // 50 µA quiescent
  float capacity_mah_ = 2000.0f;        // ~single 18650 cell
  float consumed_mah_ = 0.0f;
};

}  // namespace sim
