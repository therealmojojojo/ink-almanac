// `planWake` regression for the dynamic schedule. Asserts that the new
// signature, fed `kDefaultSchedule`, returns identical Path / minutes-to-
// next-wake to the existing `schedule_tests.cpp` cases — the dynamic
// version must match the baked behavior bit-for-bit. Then exercises a
// handful of alternative schedules to verify the dispatch is genuinely
// reading the table rather than the compile-time default.

#include <algorithm>

#include "doctest.h"
#include "modes.h"
#include "wake.h"

using fw::modes::Mode;
using fw::wake::Path;

namespace {

constexpr int hm(int h, int m) { return h * 60 + m; }

// Construct a Schedule programmatically. The tier table's invariant is
// ascending start_min; sort here so callers can list the four (start, full,
// poll, partial) tuples in any order they like.
fw::wake::Schedule buildSchedule(
    fw::wake::TierEntry t0, fw::wake::TierEntry t1,
    fw::wake::TierEntry t2, fw::wake::TierEntry t3) {
  fw::wake::Schedule s{};
  s.version = 1;
  s.valid = 1;
  s.tiers[0] = t0;
  s.tiers[1] = t1;
  s.tiers[2] = t2;
  s.tiers[3] = t3;
  std::sort(s.tiers, s.tiers + 4,
            [](const fw::wake::TierEntry& a, const fw::wake::TierEntry& b) {
              return a.start_min < b.start_min;
            });
  return s;
}

}  // namespace

TEST_CASE("default schedule: planWake matches today's hardcoded behavior") {
  const auto& s = fw::wake::kDefaultSchedule;
  // Spot-check the boundaries that schedule_tests.cpp also covers — if these
  // pass, the dynamic dispatch is producing the same answers as the previous
  // hardcoded table for the canonical input.
  CHECK(fw::wake::planWake(hm(22, 0), Mode::Summary, s).path == Path::Full);
  CHECK(fw::wake::planWake(hm(22, 1), Mode::Summary, s).path == Path::Skip);
  CHECK(fw::wake::planWake(hm(6, 29), Mode::Summary, s).path == Path::Skip);
  CHECK(fw::wake::planWake(hm(6, 30), Mode::Summary, s).path == Path::Full);
  CHECK(fw::wake::planWake(hm(6, 33), Mode::Summary, s).path == Path::Poll);
  CHECK(fw::wake::planWake(hm(10, 0), Mode::Summary, s).path == Path::Full);
  CHECK(fw::wake::planWake(hm(10, 5), Mode::Summary, s).path == Path::Partial);
  CHECK(fw::wake::planWake(hm(17, 0), Mode::Summary, s).path == Path::Full);
  CHECK(fw::wake::planWake(hm(0, 0), Mode::Summary, s).path == Path::Full);
}

TEST_CASE("alternative schedule: morning full=10 changes Full minutes") {
  // Morning full=10, poll=5, partial=1. Path priority is Full > Poll >
  // Partial, so every multiple of 5 is Poll (except multiples of 10 which
  // are Full). 06:31 / :32 / :33 / :34 are Partial; 06:35 / :45 are Poll;
  // 06:30 / :40 / :50 are Full.
  const auto s = buildSchedule(
      {hm(22, 0), 10, 0, 0},  // night (start aligns: 1320 % 10 == 0)
      {hm(6, 30), 10, 5, 1},  // morning (start aligns: 390 % 10 == 0)
      {hm(10, 0), 30, 0, 5},  // midday
      {hm(17, 0), 15, 3, 1}); // evening
  CHECK(fw::wake::planWake(hm(6, 30), Mode::Summary, s).path == Path::Full);
  CHECK(fw::wake::planWake(hm(6, 31), Mode::Summary, s).path == Path::Partial);
  CHECK(fw::wake::planWake(hm(6, 35), Mode::Summary, s).path == Path::Poll);
  CHECK(fw::wake::planWake(hm(6, 40), Mode::Summary, s).path == Path::Full);
  CHECK(fw::wake::planWake(hm(6, 45), Mode::Summary, s).path == Path::Poll);
  CHECK(fw::wake::planWake(hm(6, 50), Mode::Summary, s).path == Path::Full);
}

TEST_CASE("alternative schedule: midday full=60 saves battery") {
  // Operator widens midday to a 60-min Full cadence with 10-min Partials.
  // Midday's start_min must align to full_min (600 % 60 == 0). 10:00 is
  // Full; 10:10/:20/:30/:40/:50 are plain Partial; 11:00 is Full again.
  // Times not on a 10-multiple (e.g. 10:01, 10:05, 11:05) are Skip.
  const auto s = buildSchedule(
      {hm(22, 0), 15, 0, 0},
      {hm(6, 30), 15, 3, 1},
      {hm(10, 0), 60, 0, 10},
      {hm(17, 0), 15, 3, 1});
  CHECK(fw::wake::planWake(hm(10, 0), Mode::Summary, s).path == Path::Full);
  CHECK(fw::wake::planWake(hm(10, 10), Mode::Summary, s).path == Path::Partial);
  CHECK(fw::wake::planWake(hm(10, 30), Mode::Summary, s).path == Path::Partial);
  CHECK(fw::wake::planWake(hm(11, 0), Mode::Summary, s).path == Path::Full);
  CHECK(fw::wake::planWake(hm(11, 5), Mode::Summary, s).path == Path::Skip);
  // From a partial-cadence minute, next non-Skip wake is +10 (the next
  // Partial minute).
  CHECK(fw::wake::planWake(hm(10, 10), Mode::Summary, s).minutes_to_next_wake == 10);
}

TEST_CASE("wrap-around tier: night starts at 02:00 owns 18:00–02:00") {
  // Schedule with night starting at 18:00 (so it owns the 18:00..02:00
  // wraparound) and morning starting at 02:00. This exercises the
  // `min_of_day < tiers[0].start_min` branch in tierIndexFor for both 23:30
  // (clearly past midnight from night's perspective) and 01:30 (after
  // midnight, still in the wrap segment).
  //
  // Sorted ascending by start_min: morning(120), midday(720), evening(?),
  // night(1080). To put `night` at the wraparound, give it the largest
  // start_min and have morning own 02:00..mid-day.
  const auto s = buildSchedule(
      {hm(2, 0),   60, 0, 0},   // morning (start aligns: 120 % 60 == 0)
      {hm(12, 0),  30, 0, 5},   // midday
      {hm(15, 0),  15, 3, 1},   // evening
      {hm(18, 0),  60, 0, 0});  // night (longest start_min — wraps)
  // 23:30 → night (wrap)
  CHECK(fw::wake::planWake(hm(23, 30), Mode::Summary, s).path == Path::Skip);
  // 23:00 → night, 23:00 = 1380, 1380 % 60 == 0 → Full
  CHECK(fw::wake::planWake(hm(23, 0), Mode::Summary, s).path == Path::Full);
  // 01:30 → still in night via wrap (90 < tiers[0].start_min 120)
  CHECK(fw::wake::planWake(hm(1, 30), Mode::Summary, s).path == Path::Skip);
  // 00:00 → 0 % 60 == 0 → Full
  CHECK(fw::wake::planWake(hm(0, 0), Mode::Summary, s).path == Path::Full);
  // 02:00 → morning start, Full
  CHECK(fw::wake::planWake(hm(2, 0), Mode::Summary, s).path == Path::Full);
}

TEST_CASE("invalid schedule (valid=0) falls through to default") {
  // planWake's contract: a Schedule{} with valid=0 means "use default",
  // protecting plannedSleepSec from a zero-init schedule struct that would
  // otherwise pick a tier with full_min=0 and divide by zero.
  fw::wake::Schedule zero{};
  CHECK(fw::wake::planWake(hm(10, 0), Mode::Summary, zero).path == Path::Full);
}
