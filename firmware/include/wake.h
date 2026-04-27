#pragma once

#include <cstdint>
#include <ostream>

#include "hal/types.h"
#include "modes.h"

namespace fw::wake {

// Wake reasons. `pir` removed — motion now lives in HA (see
// openspec/changes/move-pir-to-ha-motion/); HA-driven wakes arrive as
// `HACommand`.
enum class Reason {
  ColdBoot,
  Timer,
  IMU,
  HACommand,
  SonosFastPath,
  PostOTA,
};

constexpr const char* toString(Reason r) {
  switch (r) {
    case Reason::ColdBoot:       return "cold_boot";
    case Reason::Timer:          return "timer";
    case Reason::IMU:             return "imu";
    case Reason::HACommand:       return "ha_command";
    case Reason::SonosFastPath:   return "sonos_fast_path";
    case Reason::PostOTA:         return "post_ota";
  }
  return "unknown";
}

// Persisted across deep sleeps (RTC_SLOW memory on ESP32; ordinary globals on host).
struct Persisted {
  fw::modes::Mode current_mode = fw::modes::Mode::Unknown;
  int partial_refresh_count = 0;
  // Clock zone published by the renderer for `current_mode`, fetched on
  // every Full wake from `/display/:mode/clock-zone.json`. The partial
  // path reads (x, y) and looks up the matching baked Preset by
  // `font_size`. When `font_size == 0` no zone is known (cold boot or
  // the renderer has no clock-shaped DOM element for this mode) and the
  // partial path promotes to Full.
  int16_t  clock_zone_x = 0;
  int16_t  clock_zone_y = 0;
  uint16_t clock_zone_font_size = 0;
  // Last "HH:MM" the firmware drew (either via Full's seed or via a Partial).
  // The next Partial wake re-draws these digits first, runs a partialUpdate
  // (visually a no-op — those pixels are already black on the panel), and
  // that pulse seeds the library's `DMemoryNew` previous-frame buffer so the
  // SECOND partialUpdate's diff produces correct black-to-white "clear"
  // pulses for digit positions that the new minute no longer covers.
  // 0xff means "nothing drawn yet" — cold boot before first Full lands.
  uint8_t last_drawn_hh = 0xff;
  uint8_t last_drawn_mm = 0xff;
};

Persisted& persisted();

// Host-test only: reset persisted state between scenarios.
void reset();

// Decide which wake sources to arm before the next sleep, based on the mode
// that will be resumed and the current wall-clock hour.
hal::WakeSourceMask armMask(fw::modes::Mode next_mode, int hour);

// -----------------------------------------------------------------------------
// Time-of-day wake schedule.
//
// The device wakes at minute-aligned boundaries, and which kind of wake each
// minute drives is decided by:
//   * the tier that the minute falls in (Night / Morning / Midday / Evening),
//   * the active mode (NowPlaying overrides everything to Full),
//   * cadence multiples within the tier.
//
// Wake taxonomy:
//   Full         — bring up WiFi+MQTT, fetch face PNG, full e-ink refresh,
//                  publish device state.
//   Poll         — WiFi+MQTT only; read retained active_mode. No e-ink. Used
//                  for fast entry into NowPlaying outside the forced-full
//                  cadence. If the poll detects a mode change, caller
//                  promotes the wake to Full.
//   Partial      — no network. Render the clock zone locally from baked
//                  glyphs and 1-bit partialUpdate(). Offline, ~0.06 mAh.
//   PollPartial  — combined: bring up WiFi for the mode-change check, then
//                  if no change, do a partial draw on the same wake.
//                  Used in Midday tier where the partial cadence (5 m) is
//                  long enough that piggybacking a poll is essentially free.
//   Skip         — wake fired but no work for this minute (only happens in
//                  Night, between the 15-minute fulls). Caller arms the next
//                  wake and goes straight back to sleep.
//
// Tiers (local time):
//   Night    22:00–06:30   full=15m, no poll, no partial
//   Morning  06:30–10:00   full=15m, poll=3m, partial=1m
//   Midday   10:00–17:00   full=30m, poll piggybacks partial=5m
//   Evening  17:00–22:00   same as Morning
//
// Source of truth for the schedule lives in `tierFor()` in wake.cpp. Tests in
// `firmware/test/scenarios/schedule_tests.cpp` cover each cadence case and
// boundary transition.
enum class Path { Full, Poll, Partial, PollPartial, Skip };

// `pathName` (not `toString`) so unqualified ADL inside doctest's
// `DOCTEST_STRINGIFY(toString(x))` macro does not bind here and short-circuit
// stringification with a `const char*` (which then breaks `String + char*`
// concatenation). Path stringification flows through `operator<<` instead.
constexpr const char* pathName(Path p) {
  switch (p) {
    case Path::Full:        return "full";
    case Path::Poll:        return "poll";
    case Path::Partial:     return "partial";
    case Path::PollPartial: return "poll_partial";
    case Path::Skip:        return "skip";
  }
  return "unknown";
}

inline std::ostream& operator<<(std::ostream& os, Path p) { return os << pathName(p); }

struct WakePlan {
  Path path;
  // Number of WHOLE MINUTES from the current minute to the next non-Skip
  // wake. The caller converts to seconds, subtracts seconds-into-current-
  // minute and tick-elapsed, clamps to a sane minimum, and arms the timer.
  // Always ≥ 1 (NowPlaying always returns 1; tiers with sparse cadences may
  // return up to 14 in Night).
  int minutes_to_next_wake;
};

// Pure function: given the current minute-of-day in local time (0..1439) and
// the active mode, decide what kind of wake to do and how many minutes until
// the next non-Skip wake. No I/O, no globals — everything else is the caller's
// problem (network, draw, sleep arming).
//
// `local_min_of_day` must be in [0, 1440). Out-of-range values are clamped via
// modulo so the function never returns Skip with an undefined `minutes_to_next_wake`.
WakePlan planWake(int local_min_of_day, fw::modes::Mode mode);

}  // namespace fw::wake
