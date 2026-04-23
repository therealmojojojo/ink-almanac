#include <cstdio>

#include "doctest.h"
#include "harness/Scenario.h"

// Power-budget simulation: 42 days of a realistic daily usage profile.
//
// Mode transitions at 06:30, 10:00, 22:00. Five HA-command wakes/day (driven
// by the IKEA motion sensor; equivalent to the former on-device PIR),
// two taps/day, one 45-minute Sonos session.
//
// Because the firmware main loop isn't linked in this change, we simulate
// wake durations by tagging the battery with source labels and advancing
// time deliberately. Real wake accounting lands with add-device-firmware.

namespace {

constexpr hal::Epoch SECONDS_PER_DAY = 86400;
constexpr int DAYS = 42;

void simulateDay(sim::Scenario& s, hal::Epoch day_start) {
  auto& b = s.battery();
  // Morning transition (06:30): one full Summary render.
  s.clock().advanceTo(day_start + 6 * 3600 + 30 * 60);
  b.setSource("active_summary");
  s.advanceBy(12);  // 12s wake: wifi + fetch + panel refresh
  b.setSource("deep_sleep");

  // 15-minute Summary ticks until 10:00 (14 ticks)
  for (int i = 0; i < 14; ++i) {
    s.advanceBy(15 * 60 - 12);
    b.setSource("active_summary");
    s.advanceBy(12);
    b.setSource("deep_sleep");
  }

  // 10:00 — Weather mode. 30-min ticks until 22:00 (24 ticks).
  for (int i = 0; i < 24; ++i) {
    s.advanceBy(30 * 60 - 10);
    b.setSource("active_weather");
    s.advanceBy(10);
    b.setSource("deep_sleep");
  }

  // 5 HA-command wakes (driven by the IKEA motion sensor) spaced across
  // active hours. Device still wakes briefly to fetch + draw; cost profile
  // is the same as the former on-device PIR path.
  for (int i = 0; i < 5; ++i) {
    b.setSource("ha_command_wake");
    s.advanceBy(6);
    b.setSource("deep_sleep");
  }

  // 2 tap events
  for (int i = 0; i < 2; ++i) {
    b.setSource("ha_command_wake");
    s.advanceBy(4);
    b.setSource("deep_sleep");
  }

  // 45-min Sonos session = 45 partial refreshes on track change (average).
  // Model as one "active_now_playing" burst of 45 * 6s = 270s aggregate active.
  b.setSource("active_now_playing");
  s.advanceBy(270);
  b.setSource("deep_sleep");

  // Advance to the next day
  s.clock().advanceTo(day_start + SECONDS_PER_DAY);
}

}  // namespace

TEST_CASE("power-budget: ≥20% at day 42") {
  sim::Scenario s;
  s.clock().setNow(1'744'617'600);  // 2025-04-14 06:00 UTC
  s.setBattery(100);

  hal::Epoch day_start = s.now();
  for (int d = 0; d < DAYS; ++d) {
    simulateDay(s, day_start);
    day_start += SECONDS_PER_DAY;
  }

  const int pct = s.batteryPercentage();
  std::printf("[power-budget] day 42 battery: %d%% (consumed %.1f/%.1f mAh)\n",
              pct,
              static_cast<double>(s.battery().totalConsumedMah()),
              static_cast<double>(s.battery().capacityMah()));
  CHECK(pct >= 20);
}
