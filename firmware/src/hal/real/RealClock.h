#pragma once
#ifdef ARDUINO

#include <esp_sleep.h>
#include <time.h>

#include "hal/IClock.h"

namespace fw::hal_real {

class RealClock : public hal::IClock {
 public:
  hal::Epoch nowEpoch() const override {
    time_t t = time(nullptr);
    return static_cast<hal::Epoch>(t);
  }

  // Called last in the tick — arms the timer and enters deep sleep. Does not
  // return; the ESP32 resets through setup() on next wake.
  void sleepFor(int seconds) override {
    esp_sleep_enable_timer_wakeup(static_cast<uint64_t>(seconds) * 1'000'000ull);
    esp_deep_sleep_start();
  }

  // IIMU arms its ext0 source directly in init() before we reach sleepFor;
  // nothing extra to wire here. (PIR removed — motion is HA-side.)
  void scheduleWake(hal::WakeSourceMask) override {}
};

}  // namespace fw::hal_real

#endif  // ARDUINO
