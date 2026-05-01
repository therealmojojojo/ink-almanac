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
//
// `volatile` qualifier: documented ESP32 footgun where compiler optimization
// can elide reads/writes against RTC_DATA_ATTR storage despite the bootloader
// restoring values across deep-sleep wake. See ESP32 forum thread 9407 and
// flashgamer.com's "RTC memory on ESP32 and DeepSleep gotcha". Cheap insurance.
RTC_DATA_ATTR volatile Persisted g_persisted{};
Persisted& persisted() { return const_cast<Persisted&>(g_persisted); }
#else
Persisted& persisted() {
  // Host sim: plain static. Scenarios reset state via `wake::reset()`.
  static Persisted p;
  return p;
}
#endif

void reset() { persisted() = Persisted{}; }

// -----------------------------------------------------------------------------
// Schedule planner. Pure arithmetic over minute-of-day; tier table lives below.
// Tests: firmware/test/scenarios/schedule_tests.cpp.

namespace {

struct Tier {
  uint16_t full_min;          // every Nth minute → Full (always > 0)
  uint16_t poll_min;          // standalone poll cadence; 0 = none
  uint16_t partial_min;       // partial-refresh cadence; 0 = none
  bool partial_brings_poll;   // if true, partial wakes piggyback the poll
};

// Boundaries (inclusive start, exclusive end), in minute-of-day:
//   Night    22:00–06:30  → [1320, 1440) ∪ [0, 390)
//   Morning  06:30–10:00  → [390, 600)
//   Midday   10:00–17:00  → [600, 1020)
//   Evening  17:00–22:00  → [1020, 1320)
constexpr Tier tierFor(int min_of_day) {
  if (min_of_day >= 1320 || min_of_day < 390) return {15, 0, 0, false};
  if (min_of_day < 600 || min_of_day >= 1020) return {15, 3, 1, false};
  return {30, 0, 5, true};
}

Path pathForMinute(int min_of_day, fw::modes::Mode mode) {
  // NowPlaying override — caller wants minute-fresh fetches for track changes.
  // Returned every minute; the planner schedules the next wake at +1 min.
  if (mode == fw::modes::Mode::NowPlaying) return Path::Full;

  const Tier t = tierFor(min_of_day);
  if (t.full_min && (min_of_day % t.full_min) == 0)    return Path::Full;
  if (t.poll_min && (min_of_day % t.poll_min) == 0)    return Path::Poll;
  if (t.partial_min && (min_of_day % t.partial_min) == 0) {
    return t.partial_brings_poll ? Path::PollPartial : Path::Partial;
  }
  return Path::Skip;
}

}  // namespace

WakePlan planWake(int local_min_of_day, fw::modes::Mode mode) {
  // Normalize. Negative input would break the modulo; out-of-range positive
  // input wraps to today.
  int m = local_min_of_day % 1440;
  if (m < 0) m += 1440;

  const Path path = pathForMinute(m, mode);

  // Find the next non-Skip minute. NowPlaying always returns Full at every
  // minute so the loop exits immediately; even Night (sparsest cadence)
  // crosses a Full within 14 minutes.
  for (int delta = 1; delta <= 1440; ++delta) {
    const int n = (m + delta) % 1440;
    if (pathForMinute(n, mode) != Path::Skip) {
      return {path, delta};
    }
  }

  // Unreachable — every tier has a non-zero full cadence so a Full minute
  // always exists within 24 h. Fall through with a safe default.
  return {path, 1};
}

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
