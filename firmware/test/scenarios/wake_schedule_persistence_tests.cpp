// Persistence-flow tests for the schedule cache. Exercises the RTC →
// NVS → baked-default fallback chain using the host-build stand-ins for
// RTC slow memory and NVS. The shapes match the spec:
//
//   - RTC populated → resolveSchedule returns Cache, NVS not touched.
//   - RTC empty + NVS populated → resolveSchedule returns Nvs and
//     repopulates the RTC cache as a side effect.
//   - Both empty → resolveSchedule returns Default.
//   - applySchedule writes both NVS and RTC; subsequent resolveSchedule
//     hits the cache without re-reading NVS.

#include "doctest.h"
#include "wake.h"

using fw::wake::resolveSchedule;
using fw::wake::resolveScheduleColdBoot;
using fw::wake::ScheduleSource;
using fw::wake::applySchedule;
using fw::wake::resetScheduleForTests;
using fw::wake::wipeScheduleCacheForTests;

namespace {

fw::wake::Schedule makeCustom() {
  // A trivially-valid alternative schedule, distinct from kDefaultSchedule
  // so equality checks bite when the wrong source was used.
  fw::wake::Schedule s{};
  s.version = 1;
  s.valid = 1;
  s.payload_hash = 0xDEADBEEFu;
  s.tiers[0] = {6 * 60 + 30, 10, 5, 1};   // morning
  s.tiers[1] = {10 * 60,     60, 0, 10};  // midday
  s.tiers[2] = {17 * 60,     15, 3, 1};   // evening
  s.tiers[3] = {22 * 60,     30, 0, 0};   // night
  return s;
}

}  // namespace

TEST_CASE("both layers empty: resolveSchedule falls back to Default") {
  resetScheduleForTests();
  const auto rs = resolveSchedule();
  CHECK(rs.source == ScheduleSource::Default);
  CHECK(rs.schedule.tiers[0].start_min == fw::wake::kDefaultSchedule.tiers[0].start_min);
}

TEST_CASE("applySchedule writes both layers; next resolveSchedule hits cache") {
  resetScheduleForTests();
  const auto custom = makeCustom();
  applySchedule(custom);

  const auto rs1 = resolveSchedule();
  CHECK(rs1.source == ScheduleSource::Cache);
  CHECK(rs1.schedule.payload_hash == 0xDEADBEEFu);
  CHECK(rs1.schedule.tiers[0].full_min == 10);

  // A second call still hits the cache (no NVS read needed).
  const auto rs2 = resolveSchedule();
  CHECK(rs2.source == ScheduleSource::Cache);
}

TEST_CASE("cold boot (RTC empty, NVS populated): resolveSchedule returns Nvs") {
  resetScheduleForTests();
  const auto custom = makeCustom();
  applySchedule(custom);
  // Simulate cold boot: RTC slow memory is wiped on power loss / brown-out,
  // but NVS persists. Wipe ONLY the cache.
  wipeScheduleCacheForTests();

  const auto rs = resolveSchedule();
  CHECK(rs.source == ScheduleSource::Nvs);
  CHECK(rs.schedule.payload_hash == 0xDEADBEEFu);
  CHECK(rs.schedule.tiers[1].full_min == 60);

  // Side effect: the NVS hit repopulated the RTC cache. The next call
  // should hit Cache.
  const auto rs2 = resolveSchedule();
  CHECK(rs2.source == ScheduleSource::Cache);
}

TEST_CASE("cold boot via resolveScheduleColdBoot delivers the same result") {
  resetScheduleForTests();
  const auto custom = makeCustom();
  applySchedule(custom);
  wipeScheduleCacheForTests();

  const auto rs = resolveScheduleColdBoot();
  CHECK(rs.source == ScheduleSource::Nvs);
  CHECK(rs.schedule.tiers[1].full_min == 60);
}

TEST_CASE("applySchedule rejects invalid input (valid=0) silently") {
  resetScheduleForTests();
  fw::wake::Schedule bad{};  // valid=0
  applySchedule(bad);
  // Both layers still empty → resolveSchedule still returns Default.
  CHECK(resolveSchedule().source == ScheduleSource::Default);
}
