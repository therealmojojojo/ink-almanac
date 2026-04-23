#pragma once

#include <functional>

#include "hal/IClock.h"
#include "hal/types.h"

namespace sim {

class MockBattery;  // forward decl

class MockClock : public hal::IClock {
 public:
  // Called when simulated time advances. Used by MockBattery to accumulate
  // current draw while sleeping.
  using TickCallback = std::function<void(int seconds, bool asleep)>;

  hal::Epoch nowEpoch() const override { return now_; }
  void sleepFor(int seconds) override;
  void scheduleWake(hal::WakeSourceMask mask) override { wake_mask_ = mask; }

  // Test-facing API
  void setNow(hal::Epoch e) { now_ = e; }
  void advanceBy(int seconds);
  void advanceTo(hal::Epoch target);
  hal::WakeSourceMask scheduledWakeMask() const { return wake_mask_; }
  void onTick(TickCallback cb) { tick_cb_ = std::move(cb); }

 private:
  hal::Epoch now_ = 0;
  hal::WakeSourceMask wake_mask_ = 0;
  TickCallback tick_cb_;
  void tick(int seconds, bool asleep);
};

}  // namespace sim
