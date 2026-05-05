// Schedule planner tests — verify that `fw::wake::planWake()` returns the
// right Path and minutes-to-next-wake for every cadence case and tier
// boundary. These are pure-function tests; no Scenario harness needed.

#include "doctest.h"
#include "modes.h"
#include "wake.h"

using fw::modes::Mode;
using fw::wake::Path;

namespace {

// Convenience: construct a minute-of-day from local hh:mm.
constexpr int hm(int h, int m) { return h * 60 + m; }

// Default mode for tests that aren't exercising NowPlaying.
constexpr Mode kAny = Mode::Summary;

// Wrapper that pins these tests to the baked default schedule. The
// `add-pushable-wake-schedule` change made the planner take the schedule as
// a parameter; the existing tests cover the default behavior and become
// regression coverage that the dynamic version matches the baked behavior
// for the canonical input.
fw::wake::WakePlan planWake(int min_of_day, Mode m) {
  return fw::wake::planWake(min_of_day, m, fw::wake::kDefaultSchedule);
}

}  // namespace

// -----------------------------------------------------------------------------
// Path resolution per tier.

TEST_CASE("Night tier (22:00–06:30): Full only at 15-minute multiples") {
  // 22:00 → Full
  CHECK(planWake(hm(22, 0), kAny).path == Path::Full);
  // 22:01 → Skip
  CHECK(planWake(hm(22, 1), kAny).path == Path::Skip);
  // 22:14 → Skip
  CHECK(planWake(hm(22, 14), kAny).path == Path::Skip);
  // 22:15 → Full
  CHECK(planWake(hm(22, 15), kAny).path == Path::Full);
  // 03:00 → Full (in middle of night, multiple of 15)
  CHECK(planWake(hm(3, 0), kAny).path == Path::Full);
  // 03:07 → Skip
  CHECK(planWake(hm(3, 7), kAny).path == Path::Skip);
  // 06:15 → Full (last full of Night)
  CHECK(planWake(hm(6, 15), kAny).path == Path::Full);
  // 06:29 → Skip (Night still)
  CHECK(planWake(hm(6, 29), kAny).path == Path::Skip);
}

TEST_CASE("Morning tier (06:30–10:00): Full > Poll > Partial precedence") {
  // 06:30 → Full (15-multiple AND start of Morning)
  CHECK(planWake(hm(6, 30), kAny).path == Path::Full);
  // 06:31 → Partial (1-min cadence)
  CHECK(planWake(hm(6, 31), kAny).path == Path::Partial);
  // 06:32 → Partial
  CHECK(planWake(hm(6, 32), kAny).path == Path::Partial);
  // 06:33 → Poll (3-min cadence pre-empts partial)
  CHECK(planWake(hm(6, 33), kAny).path == Path::Poll);
  // 06:34 → Partial
  CHECK(planWake(hm(6, 34), kAny).path == Path::Partial);
  // 06:36 → Poll
  CHECK(planWake(hm(6, 36), kAny).path == Path::Poll);
  // 06:45 → Full (15-multiple)
  CHECK(planWake(hm(6, 45), kAny).path == Path::Full);
  // 09:00 → Full
  CHECK(planWake(hm(9, 0), kAny).path == Path::Full);
  // 09:59 → Partial (last minute of Morning tier, partial cadence)
  CHECK(planWake(hm(9, 59), kAny).path == Path::Partial);
}

TEST_CASE("Midday tier (10:00–17:00): Full at 30, plain Partial at 5") {
  // 10:00 → Full
  CHECK(planWake(hm(10, 0), kAny).path == Path::Full);
  // 10:01 → Skip (no 1-min partial in Midday)
  CHECK(planWake(hm(10, 1), kAny).path == Path::Skip);
  // 10:04 → Skip
  CHECK(planWake(hm(10, 4), kAny).path == Path::Skip);
  // 10:05 → Partial (5-min cadence; plain offline partial — no MQTT)
  CHECK(planWake(hm(10, 5), kAny).path == Path::Partial);
  // 10:10 → Partial
  CHECK(planWake(hm(10, 10), kAny).path == Path::Partial);
  // 10:25 → Partial
  CHECK(planWake(hm(10, 25), kAny).path == Path::Partial);
  // 10:30 → Full (30-min cadence)
  CHECK(planWake(hm(10, 30), kAny).path == Path::Full);
  // 16:55 → Partial
  CHECK(planWake(hm(16, 55), kAny).path == Path::Partial);
  // 16:59 → Skip
  CHECK(planWake(hm(16, 59), kAny).path == Path::Skip);
}

TEST_CASE("Evening tier (17:00–22:00): same cadences as Morning") {
  CHECK(planWake(hm(17, 0), kAny).path == Path::Full);
  CHECK(planWake(hm(17, 1), kAny).path == Path::Partial);
  CHECK(planWake(hm(17, 3), kAny).path == Path::Poll);
  CHECK(planWake(hm(17, 15), kAny).path == Path::Full);
  CHECK(planWake(hm(21, 59), kAny).path == Path::Partial);
}

// -----------------------------------------------------------------------------
// Tier boundary transitions. The schedule's modulo math runs on
// minutes-since-midnight, so each boundary tested both sides.

TEST_CASE("06:30 boundary: last Night Skip → first Morning Full") {
  // 06:29 (Night, Skip)
  const auto a = planWake(hm(6, 29), kAny);
  CHECK(a.path == Path::Skip);
  CHECK(a.minutes_to_next_wake == 1);  // next non-Skip = 06:30 Full

  // 06:30 (Morning, Full)
  CHECK(planWake(hm(6, 30), kAny).path == Path::Full);

  // 06:31 (Morning, Partial)
  CHECK(planWake(hm(6, 31), kAny).path == Path::Partial);
}

TEST_CASE("10:00 boundary: last Morning Partial → Midday Full") {
  CHECK(planWake(hm(9, 59), kAny).path == Path::Partial);
  CHECK(planWake(hm(10, 0), kAny).path == Path::Full);
  CHECK(planWake(hm(10, 1), kAny).path == Path::Skip);
}

TEST_CASE("17:00 boundary: last Midday Skip → Evening Full") {
  CHECK(planWake(hm(16, 59), kAny).path == Path::Skip);
  CHECK(planWake(hm(17, 0), kAny).path == Path::Full);
  CHECK(planWake(hm(17, 1), kAny).path == Path::Partial);
}

TEST_CASE("22:00 boundary: last Evening Partial → Night Full") {
  CHECK(planWake(hm(21, 59), kAny).path == Path::Partial);
  CHECK(planWake(hm(22, 0), kAny).path == Path::Full);
  CHECK(planWake(hm(22, 1), kAny).path == Path::Skip);
}

TEST_CASE("midnight wrap: 23:59 → 00:00 stays in Night") {
  CHECK(planWake(hm(23, 59), kAny).path == Path::Skip);
  CHECK(planWake(hm(0, 0), kAny).path == Path::Full);  // 0 % 15 == 0
  CHECK(planWake(hm(0, 1), kAny).path == Path::Skip);
  CHECK(planWake(hm(0, 15), kAny).path == Path::Full);
}

// -----------------------------------------------------------------------------
// minutes_to_next_wake — tests the sleep alignment math.

TEST_CASE("Morning: every minute is a wake (partial cadence = 1)") {
  // From any Morning minute, next wake is +1 min.
  for (int m = hm(6, 30); m < hm(10, 0); ++m) {
    const auto p = planWake(m, kAny);
    INFO("minute = ", m);
    CHECK(p.minutes_to_next_wake == 1);
  }
}

TEST_CASE("Night: skip minutes count down to next 15-multiple") {
  // 22:00 (Full) → next at 22:15 → +15
  CHECK(planWake(hm(22, 0), kAny).minutes_to_next_wake == 15);
  // 22:01 → next at 22:15 → +14
  CHECK(planWake(hm(22, 1), kAny).minutes_to_next_wake == 14);
  // 22:14 → next at 22:15 → +1
  CHECK(planWake(hm(22, 14), kAny).minutes_to_next_wake == 1);
  // 22:15 → next at 22:30 → +15
  CHECK(planWake(hm(22, 15), kAny).minutes_to_next_wake == 15);
  // 06:15 (last Night Full) → next at 06:30 (Morning Full) → +15
  CHECK(planWake(hm(6, 15), kAny).minutes_to_next_wake == 15);
  // 06:29 (Skip, last min of Night) → next at 06:30 → +1
  CHECK(planWake(hm(6, 29), kAny).minutes_to_next_wake == 1);
}

TEST_CASE("Midday: skip minutes between 5-cadence wakes") {
  // 10:00 (Full) → next at 10:05 → +5
  CHECK(planWake(hm(10, 0), kAny).minutes_to_next_wake == 5);
  // 10:01 → next at 10:05 → +4
  CHECK(planWake(hm(10, 1), kAny).minutes_to_next_wake == 4);
  // 10:04 → next at 10:05 → +1
  CHECK(planWake(hm(10, 4), kAny).minutes_to_next_wake == 1);
  // 10:05 (Partial) → next at 10:10 → +5
  CHECK(planWake(hm(10, 5), kAny).minutes_to_next_wake == 5);
  // 10:25 (Partial) → next at 10:30 (Full) → +5
  CHECK(planWake(hm(10, 25), kAny).minutes_to_next_wake == 5);
  // 16:59 (Skip) → next at 17:00 (Evening Full) → +1
  CHECK(planWake(hm(16, 59), kAny).minutes_to_next_wake == 1);
}

// -----------------------------------------------------------------------------
// NowPlaying override.
//
// `optimise-now-playing-cadence` changed the override from Full-every-minute
// to Poll-every-minute (with conditional Full-on-track-change handled by
// the Poll handler in main_loop.cpp). The cadence (1 min) is preserved;
// the per-wake work is now mostly cheap retained-MQTT reads.

TEST_CASE("NowPlaying overrides every cadence — always Poll, +1 min") {
  // Every minute returns Poll when in NowPlaying, regardless of tier.
  for (int m : {hm(0, 0), hm(2, 30), hm(6, 29), hm(10, 1), hm(13, 14),
                hm(17, 1), hm(21, 59), hm(22, 1), hm(23, 59)}) {
    const auto p = planWake(m, Mode::NowPlaying);
    INFO("minute = ", m);
    CHECK(p.path == Path::Poll);
    CHECK(p.minutes_to_next_wake == 1);
  }
}

TEST_CASE("NowPlaying override holds at tier boundaries too") {
  CHECK(planWake(hm(6, 30), Mode::NowPlaying).path == Path::Poll);
  CHECK(planWake(hm(10, 0), Mode::NowPlaying).path == Path::Poll);
  CHECK(planWake(hm(17, 0), Mode::NowPlaying).path == Path::Poll);
  CHECK(planWake(hm(22, 0), Mode::NowPlaying).path == Path::Poll);
}

TEST_CASE("Session override forces Poll cadence regardless of mode") {
  // Even when the visible mode is Summary/Gallery (during a tap-peek), the
  // session flag keeps the planner on per-minute Poll cadence so the
  // device catches the peek-revert quickly.
  auto pw_session = [](int m, Mode mode) {
    return fw::wake::planWake(m, mode, fw::wake::kDefaultSchedule,
                              /*session_now_playing=*/true);
  };
  for (Mode m : {Mode::Summary, Mode::Gallery, Mode::Weather, Mode::Night}) {
    INFO("mode = ", static_cast<int>(m));
    const auto p = pw_session(hm(13, 14), m);  // mid-Midday (no Polls in default tier)
    CHECK(p.path == Path::Poll);
    CHECK(p.minutes_to_next_wake == 1);
  }
}

TEST_CASE("Session override off: planner follows tier dispatch") {
  // Verifies the override is gated. With session_now_playing=false and
  // mode != NowPlaying, midday (full=30, partial=5, poll=0) produces
  // plain Partial / Full / Skip — partials are always offline now.
  auto pw_no_session = [](int m, Mode mode) {
    return fw::wake::planWake(m, mode, fw::wake::kDefaultSchedule,
                              /*session_now_playing=*/false);
  };
  CHECK(pw_no_session(hm(10, 0), Mode::Summary).path == Path::Full);
  CHECK(pw_no_session(hm(10, 5), Mode::Summary).path == Path::Partial);
  CHECK(pw_no_session(hm(10, 1), Mode::Summary).path == Path::Skip);
}

// -----------------------------------------------------------------------------
// Defensive inputs.

TEST_CASE("Out-of-range minute clamps via modulo, never returns invalid plan") {
  // Negative input wraps backwards through 1440.
  const auto neg = planWake(-1, kAny);
  CHECK(neg.path == planWake(1439, kAny).path);  // -1 % 1440 = 1439

  // Very large input wraps forward.
  const auto big = planWake(10 * 1440 + hm(8, 0), kAny);
  CHECK(big.path == planWake(hm(8, 0), kAny).path);

  // minutes_to_next_wake is always ≥ 1.
  for (int m = 0; m < 1440; ++m) {
    const auto p = planWake(m, kAny);
    CHECK(p.minutes_to_next_wake >= 1);
    CHECK(p.minutes_to_next_wake <= 30);  // Midday: 30-min full is the longest gap
  }
}

// -----------------------------------------------------------------------------
// Whole-day audit. Walk every minute of every tier; assert each minute's path
// matches what the tier table prescribes. This catches off-by-one tier
// boundary errors and modulo bugs in one sweep.

TEST_CASE("whole-day path audit: Night minutes are Full xor Skip") {
  for (int m = 0; m < hm(6, 30); ++m) {
    const auto p = planWake(m, kAny).path;
    INFO("Night minute ", m);
    if (m % 15 == 0) CHECK(p == Path::Full);
    else             CHECK(p == Path::Skip);
  }
  for (int m = hm(22, 0); m < 1440; ++m) {
    const auto p = planWake(m, kAny).path;
    INFO("Night minute ", m);
    if (m % 15 == 0) CHECK(p == Path::Full);
    else             CHECK(p == Path::Skip);
  }
}

TEST_CASE("whole-day path audit: Morning minutes follow Full>Poll>Partial") {
  for (int m = hm(6, 30); m < hm(10, 0); ++m) {
    const auto p = planWake(m, kAny).path;
    INFO("Morning minute ", m);
    if      (m % 15 == 0) CHECK(p == Path::Full);
    else if (m % 3 == 0)  CHECK(p == Path::Poll);
    else                   CHECK(p == Path::Partial);
  }
}

TEST_CASE("whole-day path audit: Midday minutes follow Full>Partial>Skip") {
  for (int m = hm(10, 0); m < hm(17, 0); ++m) {
    const auto p = planWake(m, kAny).path;
    INFO("Midday minute ", m);
    if      (m % 30 == 0) CHECK(p == Path::Full);
    else if (m % 5 == 0)  CHECK(p == Path::Partial);
    else                   CHECK(p == Path::Skip);
  }
}

TEST_CASE("whole-day path audit: Evening matches Morning") {
  for (int m = hm(17, 0); m < hm(22, 0); ++m) {
    const auto p = planWake(m, kAny).path;
    INFO("Evening minute ", m);
    if      (m % 15 == 0) CHECK(p == Path::Full);
    else if (m % 3 == 0)  CHECK(p == Path::Poll);
    else                   CHECK(p == Path::Partial);
  }
}
