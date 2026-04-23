#include "hal/mock/MockClock.h"

namespace sim {

void MockClock::sleepFor(int seconds) {
  tick(seconds, /*asleep=*/true);
}

void MockClock::advanceBy(int seconds) {
  tick(seconds, /*asleep=*/false);
}

void MockClock::advanceTo(hal::Epoch target) {
  if (target <= now_) return;
  tick(static_cast<int>(target - now_), /*asleep=*/false);
}

void MockClock::tick(int seconds, bool asleep) {
  if (seconds <= 0) return;
  now_ += seconds;
  if (tick_cb_) tick_cb_(seconds, asleep);
}

}  // namespace sim
