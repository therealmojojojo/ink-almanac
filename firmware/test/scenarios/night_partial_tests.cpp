// Night-mode partial-refresh scenarios (add-night-text-clock-partials).
//
// Verifies the firmware's phrase-clock partial path:
//   - Cold-boot Full at a non-phrase minute leaves `last_drawn_phrase_min`
//     at the sentinel (no post-cleanup over-paint of the PNG's text).
//   - Timer wake at a partial-eligible minute (e.g. 22:15) dispatches to
//     doPartialNight, calls phraseForMinute, blits the bitmap via
//     drawBitmap1Bit, runs 2× partialUpdate1Bit (cold wipe + draw), and
//     returns true (no Full promotion, no WiFi/MQTT).
//   - Warm partial (consecutive partials) seeds DMemoryNew with the
//     previously-drawn phrase before blitting the current minute's.
//   - Off-cadence minute (03:07) under 120/0/15 returns Skip — verified
//     via the existing planner; this file just confirms the partial
//     code path doesn't accidentally trigger.
//   - The generated phraseForMinute table has exactly the 25 expected
//     entries.

#include <cstdint>
#include <vector>

#include "config.h"
#include "doctest.h"
#include "firmware.h"
#include "generated/night_phrases.h"
#include "harness/Scenario.h"
#include "modes.h"
#include "wake.h"

namespace {

struct ResetFirmwareState {
  ResetFirmwareState() {
    fw::wake::reset();
    fw::wake::resetScheduleForTests();
  }
};

#define SIM_RESET() ResetFirmwareState _reset_

// Returns a UTC epoch such that, after the firmware applies
// `+ kTzOffsetSec = +3h`, `gmtime(local_now)` reports the requested local
// hour:minute on 2025-04-14. (main_loop_tests.cpp has a parallel helper
// with a 2-hour offset error in its kApr14_0800 base that other tests
// don't notice — they only check cadence-modulo behavior. This file
// asserts on absolute min-of-day so it needs the wall clock correct.)
//
// 1744617600 = 2025-04-14 08:00:00 UTC. To make local_now read as
// (local_h, local_m) after the +3h add, set nowEpoch = the UTC moment
// (local_h - 3, local_m) on the same day.
constexpr hal::Epoch kApr14_0000utc = 1'744'617'600 - 8 * 3600;  // 2025-04-14 00:00 UTC
constexpr hal::Epoch localTime(int local_h, int local_m) {
  // Subtract the TZ offset so that gmtime(now + 3h) yields (local_h, local_m).
  const int seconds = ((local_h - 3) * 3600 + local_m * 60);
  return kApr14_0000utc + static_cast<hal::Epoch>(seconds);
}

std::vector<uint8_t> fakePng(std::size_t n = 1024, uint8_t fill = 0x80) {
  return std::vector<uint8_t>(n, fill);
}

std::string urlFor(const char* mode) {
  return std::string("http://renderer.local:8575/display/") + mode + ".png";
}

std::string clockZoneUrlFor(const char* mode) {
  return std::string("http://renderer.local:8575/display/") + mode + "/clock-zone.json";
}

// Inject the operator's deployed 120/0/15 Night cadence. Other tiers use
// the kDefaultSchedule values so the morning/midday/evening cadences in
// these tests match what the production planner would do.
void apply120015NightSchedule() {
  fw::wake::Schedule s = fw::wake::kDefaultSchedule;
  s.tiers[3].full_min = 120;
  s.tiers[3].partial_min = 15;
  // 0xC0FFEE is just a distinctive non-zero hash so the test schedule is
  // identifiable in any future debug-ring inspection; the firmware uses it
  // only to dedup against MQTT republishes, which these tests don't do.
  s.payload_hash = 0xC0FFEEu;
  fw::wake::applySchedule(s);
}

// Stub the Night face's clock-zone JSON. Numbers match what the live
// renderer would emit for `.night-phrase` (large x near left, y near top
// of the face, w/h sized for the 220u flex container).
void stubNightClockZone(sim::Scenario& s) {
  const std::string json =
      "{\"x\":86,\"y\":54,\"w\":900,\"h\":220,\"font_size\":96}";
  std::vector<uint8_t> bytes(json.begin(), json.end());
  s.transport().setRendererResponse(clockZoneUrlFor("night"), std::move(bytes), 200);
}

void coldBootNightAt(sim::Scenario& s, int local_h, int local_m) {
  apply120015NightSchedule();
  s.clock().setNow(localTime(local_h, local_m));
  s.mqttPublish(fw::config::kTopicActiveMode, "night", /*retained=*/true)
      .setRendererResponse(urlFor("night"), fakePng());
  stubNightClockZone(s);
  fw::tick(s.hal(), fw::wake::Reason::ColdBoot);
}

}  // namespace

TEST_CASE("phraseForMinute exposes exactly the 25 partial-eligible minutes") {
  // The 25 minutes the bake tool emitted: Night tier (22:00 → 06:30) ∩
  // every 15 min ∩ NOT a multiple of 60. Equivalently: every :15/:30/:45
  // in 22:xx, 23:xx, 00:xx … 05:xx, plus 06:15 (the only Night-tier
  // partial in the 06:00–06:30 window before Morning takes over).
  const std::vector<int> expected = {
      15,   30,   45,                 // 00:15, 00:30, 00:45
      75,   90,  105,                 // 01:xx
     135,  150,  165,                 // 02:xx
     195,  210,  225,                 // 03:xx
     255,  270,  285,                 // 04:xx
     315,  330,  345,                 // 05:xx
     375,                             // 06:15 (only partial in 06:xx)
    1335, 1350, 1365,                 // 22:xx
    1395, 1410, 1425,                 // 23:xx
  };
  REQUIRE(expected.size() == 25);
  for (int min : expected) {
    CAPTURE(min);
    CHECK(fw::night_phrases::phraseForMinute(min) != nullptr);
  }
  // Spot-check non-partial minutes.
  for (int min : {0, 60, 120, 720, 7, 22, 47, 1320, 30 + 1, 60 + 7}) {
    CAPTURE(min);
    CHECK(fw::night_phrases::phraseForMinute(min) == nullptr);
  }
}

TEST_CASE("baked phrase bitmaps have reasonable dimensions") {
  // Sanity: each entry has non-zero width/height and a non-null data
  // pointer. Catches a future bake regression that emits a zero-sized
  // entry or forgets the data array.
  for (int min : {15, 1335, 375, 195}) {
    CAPTURE(min);
    const auto* bm = fw::night_phrases::phraseForMinute(min);
    REQUIRE(bm != nullptr);
    CHECK(bm->width > 100);     // shortest phrase "half past two" is wider than this
    CHECK(bm->width < 1100);    // longest fits within the 1200u panel width
    CHECK(bm->height > 40);     // tight bbox of 96px italic ink is at least this tall
    CHECK(bm->height < 200);    // and not wider than the 220u zone
    CHECK(bm->data != nullptr);
  }
}

TEST_CASE("Night cold-boot Full at 22:00 leaves phrase-min sentinel for first partial") {
  // 22:00 is a Full minute under 120/0/15 — `min_of_day == 1320`,
  // 1320 % 120 == 0 → Full. But 22:00 is NOT in the partial-phrase
  // set (phraseForMinute(1320) == nullptr), so the post-Full cleanup
  // is a no-op for the over-paint. The renderer's night.png renders
  // "ten o'clock" via 3-bit text; that stands on the panel until the
  // 22:15 partial wipes it.
  SIM_RESET();
  sim::Scenario s;
  coldBootNightAt(s, 22, 0);

  CHECK(s.display().fullRefreshCount() > 0);
  // Sentinel preserved → next partial knows it's in the cold state.
  CHECK(fw::wake::persisted().last_drawn_phrase_min == 0xffff);
  CHECK(static_cast<int>(fw::wake::persisted().current_mode) ==
        static_cast<int>(fw::modes::Mode::Night));
  // Clock zone was fetched and parsed (w/h carried through the new
  // fields added by add-night-text-clock-partials).
  CHECK(fw::wake::persisted().clock_zone_h == 220);
  CHECK(fw::wake::persisted().clock_zone_w == 900);
}

TEST_CASE("Timer @ Night 22:15 → Partial blits phrase bitmap, no Full promotion") {
  SIM_RESET();
  sim::Scenario s;
  coldBootNightAt(s, 22, 0);

  const int full_after_boot = s.display().fullRefreshCount();
  const int partial_after_boot = s.display().partialUpdate1BitCount();
  const auto blits_after_boot = s.display().bitmapBlits().size();
  const auto state_pubs_after_boot =
      s.publishedMessages(fw::config::kTopicDeviceState).size();

  // 22:15 — Night partial-eligible minute. Cold state: 1 wipe-pulse +
  // 1 blit + 1 partialUpdate (= 2 partial updates total; the wipe IS a
  // partialUpdate. Cycles assertion is structural, not pixel-exact).
  s.clock().setNow(localTime(22, 15));
  fw::tick(s.hal(), fw::wake::Reason::Timer);

  // No Full promotion — Partial succeeded.
  CHECK(s.display().fullRefreshCount() == full_after_boot);
  // No new device-state publish (no MQTT in the Partial path).
  CHECK(s.publishedMessages(fw::config::kTopicDeviceState).size() == state_pubs_after_boot);
  // Two partialUpdate calls: cold-wipe pulse + draw pulse.
  CHECK(s.display().partialUpdate1BitCount() - partial_after_boot == 2);
  // At least one bitmap blit landed (the phrase blit at 22:15 ==
  // min_of_day 1335 = "quarter past ten"). The fillRect1Bit pulse also
  // records into bitmapBlits, so the count is ≥ 2 (rect + bitmap).
  CHECK(s.display().bitmapBlits().size() > blits_after_boot);
  // Persisted advanced from sentinel to 22:15's min_of_day.
  CHECK(fw::wake::persisted().last_drawn_phrase_min == 22 * 60 + 15);
}

TEST_CASE("Consecutive Night partials seed DMemoryNew with previous phrase") {
  // 22:00 cold-boot Full (sentinel) → 22:15 partial (cold-state wipe +
  // draw; sets last_drawn_phrase_min = 1335) → 22:30 partial (warm-state
  // seed-then-draw; sees last_drawn_phrase_min == 1335 on entry and
  // updates to 1350 on exit).
  SIM_RESET();
  sim::Scenario s;
  coldBootNightAt(s, 22, 0);

  s.clock().setNow(localTime(22, 15));
  fw::tick(s.hal(), fw::wake::Reason::Timer);
  REQUIRE(fw::wake::persisted().last_drawn_phrase_min == 22 * 60 + 15);

  const int partial_before_30 = s.display().partialUpdate1BitCount();
  const auto blits_before_30 = s.display().bitmapBlits().size();

  s.clock().setNow(localTime(22, 30));
  fw::tick(s.hal(), fw::wake::Reason::Timer);

  // Warm state at 22:30: seed (previous phrase blit) + draw (new phrase
  // blit) = 2 partialUpdate1Bit calls.
  CHECK(s.display().partialUpdate1BitCount() - partial_before_30 == 2);
  // Each nightBlit() does a zone-wide fillRect1Bit(white) clear before
  // drawBitmap1Bit, so the diff against the prior DMemoryNew includes
  // both old-only pixels (transition black→white) and new-only pixels
  // (white→black) in one waveform cycle. The MockDisplay records both
  // the fillRect and the drawBitmap into bitmap_blits_, so a warm-state
  // partial produces 2 × 2 = 4 entries (seed-clear + seed-draw +
  // new-clear + new-draw). No black-wipe fillRect (we're past cold state).
  CHECK(s.display().bitmapBlits().size() - blits_before_30 == 4);
  CHECK(fw::wake::persisted().last_drawn_phrase_min == 22 * 60 + 30);
}

TEST_CASE("Timer @ Night :07 under 120/0/15 → Skip (off-cadence) — sanity") {
  // 22:07 is not a multiple of 15 → not Partial-eligible under 120/0/15.
  // The planner returns Skip; tick() re-arms and sleeps without touching
  // the panel. Guards against a future planner regression that would
  // accidentally route off-cadence minutes into doPartial.
  SIM_RESET();
  sim::Scenario s;
  coldBootNightAt(s, 22, 0);

  const int full_after = s.display().fullRefreshCount();
  const int partial_after = s.display().partialUpdate1BitCount();
  const auto blits_after = s.display().bitmapBlits().size();

  s.clock().setNow(localTime(22, 7));
  fw::tick(s.hal(), fw::wake::Reason::Timer);

  CHECK(s.display().fullRefreshCount() == full_after);
  CHECK(s.display().partialUpdate1BitCount() == partial_after);
  CHECK(s.display().bitmapBlits().size() == blits_after);
}
