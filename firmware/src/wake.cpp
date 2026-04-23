#include "wake.h"

#ifdef ARDUINO
#include <esp_attr.h>
#endif

#include "config.h"

namespace fw::wake {

#ifdef ARDUINO
// RTC slow memory survives deep sleep (but not power-off / reflash). Holding
// `current_mode` here lets the minute-tick early-return work: on a normal
// timer wake the resolved `active_mode` matches the stored one, no full
// refresh is scheduled, and the partial-refresh counter continues toward the
// ghost-clear threshold.
RTC_DATA_ATTR Persisted g_persisted{};
Persisted& persisted() { return g_persisted; }
#else
Persisted& persisted() {
  // Host sim: plain static. Scenarios reset state via `wake::reset()`.
  static Persisted p;
  return p;
}
#endif

void reset() { persisted() = Persisted{}; }

hal::WakeSourceMask armMask(fw::modes::Mode next_mode, int hour) {
  using namespace fw::config;
  hal::WakeSourceMask mask = 0;

  // Timer wake whenever the mode has one.
  if (fw::modes::timerSeconds(next_mode) > 0) {
    mask |= static_cast<hal::WakeSourceMask>(hal::WakeSource::Timer);
  }

  // IMU INT is always armed so the device responds to taps at all times.
  mask |= static_cast<hal::WakeSourceMask>(hal::WakeSource::IMU);

  // Sonos fast-path: during Sonos window, a shorter timer replaces the mode timer
  // for fast-path wake. Encoded implicitly via the caller passing kSonosFastPathSec.
  (void)kSonosFastPathSec;

  // `hour` is unused now that PIR quiet-hours arming moved to HA. Keep the
  // parameter so callers don't change; silence the warning.
  (void)hour;

  return mask;
}

}  // namespace fw::wake
