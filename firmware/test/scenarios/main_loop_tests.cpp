#include <cstdint>
#include <vector>

#include "config.h"
#include "doctest.h"
#include "firmware.h"
#include "harness/Scenario.h"
#include "modes.h"
#include "wake.h"

namespace {
struct ResetFirmwareState {
  ResetFirmwareState() { fw::wake::reset(); }
};
}  // namespace

#define SIM_RESET() ResetFirmwareState _reset_

namespace {

// Construct a fake PNG payload of the given size. Content is irrelevant; the
// firmware only hashes it and forwards bytes to drawImage.
std::vector<uint8_t> fakePng(std::size_t n = 1024, uint8_t fill = 0x80) {
  return std::vector<uint8_t>(n, fill);
}

constexpr hal::Epoch kApr14_0800 = 1'744'617'600 + 2 * 3600;  // 08:00 UTC

// Returns a UTC epoch for a given LOCAL time on Apr 14 (config TZ = UTC+3).
// kApr14_0800 (08:00 UTC) is 11:00 local → minute-of-day 660. Offsets from
// there are easy to reason about and stable across test runs.
constexpr hal::Epoch localTime(int local_h, int local_m) {
  return kApr14_0800 +
         static_cast<hal::Epoch>((local_h * 60 + local_m - 11 * 60) * 60);
}

std::string urlFor(const char* mode) {
  return std::string("http://renderer.local:8575/display/") + mode + ".png";
}

std::string clockZoneUrlFor(const char* mode) {
  return std::string("http://renderer.local:8575/display/") + mode + "/clock-zone.json";
}

// Default clock zone for tests. Matches the Compact preset's font_size (44)
// so the firmware's presetByFontSize lookup returns a real StringPreset and
// the partial path runs. The Summary face's 160px clock is intentionally not
// in the baked PRESETS list (flash budget), so a font_size=160 stub would
// always fall through to Full and most partial-path scenarios would skip.
// Tests don't depend on which face the font_size belongs to in the live UI.
void stubClockZone(sim::Scenario& s, const char* mode, int x, int y, int font_size) {
  const std::string json =
      std::string("{\"x\":") + std::to_string(x) +
      ",\"y\":" + std::to_string(y) +
      ",\"w\":545,\"h\":144,\"font_size\":" + std::to_string(font_size) + "}";
  std::vector<uint8_t> bytes(json.begin(), json.end());
  s.transport().setRendererResponse(clockZoneUrlFor(mode), std::move(bytes), 200);
}

// Helper: arrange a successful prior cold-boot so persisted.current_mode is
// set to `mode` and the panel has done one full refresh. Stubs both the PNG
// and the clock-zone JSON so the post-Full clock-zone fetch populates
// persisted.clock_zone_*.
void coldBootInto(sim::Scenario& s, const char* mode, int font_size = 44) {
  s.mqttPublish(fw::config::kTopicActiveMode, mode, /*retained=*/true)
      .setRendererResponse(urlFor(mode), fakePng());
  stubClockZone(s, mode, /*x=*/48, /*y=*/73, font_size);
  fw::tick(s.hal(), fw::wake::Reason::ColdBoot);
}

}  // namespace

TEST_CASE("cold boot: full refresh + device state publish") {
  SIM_RESET();
  sim::Scenario s;
  s.clock().setNow(kApr14_0800);
  s.setBattery(95)
      .mqttPublish(fw::config::kTopicActiveMode, "summary", /*retained=*/true)
      .setRendererResponse(urlFor("summary"), fakePng());

  fw::tick(s.hal(), fw::wake::Reason::ColdBoot);

  CHECK(s.display().fullRefreshCount() == 1);
  CHECK(s.display().calls().back().full == true);
  auto pubs = s.publishedMessages(fw::config::kTopicDeviceState);
  REQUIRE(pubs.size() >= 1);
  CHECK(pubs.back().retained == true);
  // Wake mask: IMU always armed, Timer armed for this mode. PIR removed —
  // motion is HA-side.
  const auto mask = s.wakeSourcesArmed();
  CHECK((mask & static_cast<hal::WakeSourceMask>(hal::WakeSource::IMU)) != 0);
  CHECK((mask & static_cast<hal::WakeSourceMask>(hal::WakeSource::Timer)) != 0);
}

TEST_CASE("timer wake always full-refreshes on Inkplate 10 (3-bit grayscale)") {
  // The Soldered Inkplate library's partialUpdate() is a no-op when the
  // panel is in 3-bit mode (which we need for the grayscale corpus images),
  // so the firmware refreshes full on every wake — clock zone advances at
  // the wake cadence. See main_loop.cpp "Refresh policy" comment.
  SIM_RESET();
  sim::Scenario s;
  s.clock().setNow(kApr14_0800);
  s.mqttPublish(fw::config::kTopicActiveMode, "summary", true)
      .setRendererResponse(urlFor("summary"), fakePng());
  fw::tick(s.hal(), fw::wake::Reason::ColdBoot);
  const int full_after_first = s.display().fullRefreshCount();

  // Minute-tick wake, same mode → FULL refresh + state publish (clock tick).
  const auto state_pubs_before = s.publishedMessages(fw::config::kTopicDeviceState).size();
  fw::tick(s.hal(), fw::wake::Reason::Timer);
  CHECK(s.display().fullRefreshCount() == full_after_first + 1);
  CHECK(s.display().partialRefreshCount() == 0);
  CHECK(s.publishedMessages(fw::config::kTopicDeviceState).size() == state_pubs_before + 1);

  // Mode change on next wake → another full refresh.
  s.mqttPublish(fw::config::kTopicActiveMode, "weather", true);
  s.setRendererResponse(urlFor("weather"), fakePng());
  fw::tick(s.hal(), fw::wake::Reason::Timer);
  CHECK(s.display().fullRefreshCount() == full_after_first + 2);
}

TEST_CASE("quiet hours: IMU stays armed, no PIR slot exists") {
  SIM_RESET();
  sim::Scenario s;
  // Set time to 02:00 UTC — inside quiet window [00,05). IMU INT is always
  // armed; the PIR slot was removed with the HA-motion migration.
  s.clock().setNow(1'744'617'600 - 4 * 3600);
  s.mqttPublish(fw::config::kTopicActiveMode, "night", true)
      .setRendererResponse(urlFor("night"), fakePng());
  fw::tick(s.hal(), fw::wake::Reason::ColdBoot);
  const auto mask = s.wakeSourcesArmed();
  CHECK((mask & static_cast<hal::WakeSourceMask>(hal::WakeSource::IMU)) != 0);
}

TEST_CASE("renderer unreachable shows an indicator and publishes device state anyway") {
  SIM_RESET();
  sim::Scenario s;
  s.clock().setNow(kApr14_0800);
  s.mqttPublish(fw::config::kTopicActiveMode, "summary", true);
  // No setRendererResponse — transport returns 404.
  fw::tick(s.hal(), fw::wake::Reason::Timer);

  // An indicator drawImage happened (partial, 80×80).
  CHECK(s.display().partialRefreshCount() >= 1);
  CHECK(s.display().fullRefreshCount() == 0);
  // Device state still published.
  CHECK(!s.publishedMessages(fw::config::kTopicDeviceState).empty());
}

TEST_CASE("sonos fast-path with unchanged mode full-refreshes (clock tick)") {
  // Same hardware constraint as the timer-wake case: 3-bit mode means full
  // refresh on every redraw.
  SIM_RESET();
  sim::Scenario s;
  s.clock().setNow(kApr14_0800);
  s.mqttPublish(fw::config::kTopicActiveMode, "summary", true)
      .setRendererResponse(urlFor("summary"), fakePng());
  fw::tick(s.hal(), fw::wake::Reason::ColdBoot);
  const int full_before = s.display().fullRefreshCount();

  // Same mode, fast-path wake → another FULL refresh (clock tick).
  fw::tick(s.hal(), fw::wake::Reason::SonosFastPath);
  CHECK(s.display().fullRefreshCount() == full_before + 1);
  CHECK(s.display().partialRefreshCount() == 0);
}

// -----------------------------------------------------------------------------
// Gesture grace-window tests (add-local-clock-tick "Tap detection")
// -----------------------------------------------------------------------------

TEST_CASE("IMU wake: gesture published before active_mode resolved") {
  SIM_RESET();
  sim::Scenario s;
  s.clock().setNow(kApr14_0800);
  // Pre-gesture retained state: device was on summary.
  s.mqttPublish(fw::config::kTopicActiveMode, "summary", true)
      .setRendererResponse(urlFor("summary"), fakePng())
      .setRendererResponse(urlFor("weather"), fakePng());
  // Cold boot first so last-drawn mode is summary.
  fw::tick(s.hal(), fw::wake::Reason::ColdBoot);
  const int full_before = s.display().fullRefreshCount();

  // Simulate HA: when the device publishes the gesture, HA reacts by
  // pushing the new face on the non-retained gesture_response event topic
  // (so the device's grace-window wait sees a fresh push, not a stale
  // retained value) AND updating retained active_mode for subsequent Fulls.
  auto& t = s.transport();
  t.setPublishHook([&t](const sim::MockTransport::Publish& p) {
    if (p.topic == fw::config::kTopicGesture) {
      t.mqttPublish(fw::config::kTopicGestureResponse, "weather", /*retained=*/false);
      t.mqttPublish(fw::config::kTopicActiveMode, "weather", /*retained=*/true);
    }
  });

  // Fire a single tap + IMU wake.
  s.fireTap(/*isDouble=*/false);
  fw::tick(s.hal(), fw::wake::Reason::IMU);

  // Gesture was published exactly once.
  auto gestures = s.publishedMessages(fw::config::kTopicGesture);
  REQUIRE(gestures.size() == 1);
  CHECK(gestures[0].payload.find("single") != std::string::npos);
  // Device picked up HA's decision inside the grace window and drew Weather.
  CHECK(s.display().fullRefreshCount() > full_before);
}

TEST_CASE("IMU wake: HA silent → keep pre-gesture face") {
  SIM_RESET();
  sim::Scenario s;
  s.clock().setNow(kApr14_0800);
  s.mqttPublish(fw::config::kTopicActiveMode, "summary", true)
      .setRendererResponse(urlFor("summary"), fakePng());
  fw::tick(s.hal(), fw::wake::Reason::ColdBoot);
  const int full_before = s.display().fullRefreshCount();

  // No publish hook — HA doesn't respond to the gesture.
  s.fireTap(/*isDouble=*/false);
  fw::tick(s.hal(), fw::wake::Reason::IMU);

  auto gestures = s.publishedMessages(fw::config::kTopicGesture);
  REQUIRE(gestures.size() == 1);
  // Mode unchanged (still summary from the cold-boot retained value). On
  // 3-bit Inkplate 10 every redraw is full anyway (partial is a hardware
  // no-op), so the IMU wake still drives a full refresh — same face, but
  // the clock zone advances.
  CHECK(s.display().fullRefreshCount() == full_before + 1);
}

TEST_CASE("IMU wake during quiet hours: HA holds Night, no face change") {
  SIM_RESET();
  sim::Scenario s;
  // 02:00 UTC — within quiet hours.
  s.clock().setNow(1'744'617'600 - 4 * 3600);
  s.mqttPublish(fw::config::kTopicActiveMode, "night", true)
      .setRendererResponse(urlFor("night"), fakePng());
  fw::tick(s.hal(), fw::wake::Reason::ColdBoot);
  const int full_before = s.display().fullRefreshCount();

  // Simulate HA's quiet-hours guard: gesture arrives but the gesture handler
  // bails on its quiet-hours condition, so no gesture_response push fires.
  // The device's grace-window wait times out, falls back to resolveActiveMode
  // which reads retained active_mode = "night" (unchanged from cold-boot
  // setup), and renders Night — same face, no visible change.
  auto& t = s.transport();
  t.setPublishHook([](const sim::MockTransport::Publish&) {});

  s.fireTap(/*isDouble=*/false);
  fw::tick(s.hal(), fw::wake::Reason::IMU);

  auto gestures = s.publishedMessages(fw::config::kTopicGesture);
  REQUIRE(gestures.size() == 1);
  // Same face, but on 3-bit Inkplate 10 every wake redraws (partial is a
  // hardware no-op) — so a full refresh still happens, with the same content.
  CHECK(s.display().fullRefreshCount() == full_before + 1);
}

TEST_CASE("IMU wake: double tap gesture payload") {
  SIM_RESET();
  sim::Scenario s;
  s.clock().setNow(kApr14_0800);
  s.mqttPublish(fw::config::kTopicActiveMode, "gallery", true)
      .setRendererResponse(urlFor("gallery"), fakePng())
      .setRendererResponse(urlFor("summary"), fakePng());
  fw::tick(s.hal(), fw::wake::Reason::ColdBoot);

  auto& t = s.transport();
  t.setPublishHook([&t](const sim::MockTransport::Publish& p) {
    if (p.topic == fw::config::kTopicGesture &&
        p.payload.find("double") != std::string::npos) {
      // HA's summary_gallery_toggle: Gallery → Summary.
      t.mqttPublish(fw::config::kTopicGestureResponse, "summary", /*retained=*/false);
      t.mqttPublish(fw::config::kTopicActiveMode, "summary", /*retained=*/true);
    }
  });

  s.fireTap(/*isDouble=*/true);
  fw::tick(s.hal(), fw::wake::Reason::IMU);

  auto gestures = s.publishedMessages(fw::config::kTopicGesture);
  REQUIRE(gestures.size() == 1);
  CHECK(gestures[0].payload.find("double") != std::string::npos);
}

// =============================================================================
// Path-routed wakes (Phase 4: planWake-driven dispatch in tick()).
//
// Every test below cold-boots into a known mode at a known local time, then
// issues a Timer wake at a different minute that lands on a specific tier
// cadence. Assertions cover the path-specific side effects: who connected to
// WiFi/MQTT, whether the e-ink panel was refreshed (full or 1-bit partial),
// and whether device-state was published.
//
// Local time is derived from the firmware's `kTzOffsetSec` (UTC+3); helpers
// `localTime(h, m)` and `coldBootInto(...)` are defined at the top of this
// file.

TEST_CASE("Timer @ Morning :01 → Partial — clock-only, no network") {
  SIM_RESET();
  sim::Scenario s;
  // Cold-boot at local 06:30 (Morning Full minute) so persisted.current_mode
  // = Summary and the panel is initialised. Cold boot does the Full draw
  // PLUS a post-Full zone cleanup (solid-black pulse + clean-to-white pulse
  // with the new digits) so subsequent partial wakes can diff cleanly. That
  // cleanup also sets last_drawn to the Full's HH:MM, so this first partial
  // DOES seed against last_drawn rather than skipping the seed step.
  s.clock().setNow(localTime(6, 30));
  coldBootInto(s, "summary");
  const int full_after_boot = s.display().fullRefreshCount();
  const int partial_after_boot = s.display().partialUpdate1BitCount();
  const auto blits_after_boot = s.display().bitmapBlits().size();
  const auto mode_history_after_boot = s.display().displayModeHistory().size();
  const auto state_pubs_after_boot =
      s.publishedMessages(fw::config::kTopicDeviceState).size();

  // Advance to local 06:31. Partial cadence (1-min) lands here.
  s.clock().setNow(localTime(6, 31));

  fw::tick(s.hal(), fw::wake::Reason::Timer);

  // Seed-then-draw partial wake: 12 blits (2 × (fillRect + 5 glyphs)),
  // 2 partialUpdates.
  CHECK(s.display().bitmapBlits().size() - blits_after_boot == 12);
  CHECK(s.display().partialUpdate1BitCount() - partial_after_boot == 2);
  // Mode flipped to OneBit, then back to ThreeBit (one pair per partial wake).
  REQUIRE(s.display().displayModeHistory().size() - mode_history_after_boot == 2);
  // No full refresh, no device-state publish (offline path).
  CHECK(s.display().fullRefreshCount() == full_after_boot);
  CHECK(s.publishedMessages(fw::config::kTopicDeviceState).size() == state_pubs_after_boot);
}

TEST_CASE("Timer @ Morning :02 after :01 partial → seed-then-draw (12 blits)") {
  SIM_RESET();
  sim::Scenario s;
  s.clock().setNow(localTime(6, 30));
  coldBootInto(s, "summary");
  // First partial wake at 06:31 — seeds last_drawn = 06:31.
  s.clock().setNow(localTime(6, 31));
  fw::tick(s.hal(), fw::wake::Reason::Timer);
  const int partial_after_first = s.display().partialUpdate1BitCount();
  const auto blits_after_first = s.display().bitmapBlits().size();

  // Second partial wake at 06:32 — last_drawn = 06:31, so seed step runs.
  s.clock().setNow(localTime(6, 32));
  fw::tick(s.hal(), fw::wake::Reason::Timer);

  CHECK(s.display().bitmapBlits().size() - blits_after_first == 12);
  CHECK(s.display().partialUpdate1BitCount() - partial_after_first == 2);
}

TEST_CASE("Timer @ Morning :03 → Poll — MQTT read + clock partial (no Full)") {
  SIM_RESET();
  sim::Scenario s;
  s.clock().setNow(localTime(6, 30));
  coldBootInto(s, "summary");
  const int full_after_boot = s.display().fullRefreshCount();
  const int partial_after_boot = s.display().partialUpdate1BitCount();
  const auto blits_after_boot = s.display().bitmapBlits().size();
  const auto state_pubs_after_boot =
      s.publishedMessages(fw::config::kTopicDeviceState).size();

  // Advance to 06:33 — poll cadence (3-min) hits, partial doesn't.
  s.clock().setNow(localTime(6, 33));

  fw::tick(s.hal(), fw::wake::Reason::Timer);

  // No Full and no device-state publish (Poll without mode change).
  CHECK(s.display().fullRefreshCount() == full_after_boot);
  CHECK(s.publishedMessages(fw::config::kTopicDeviceState).size() == state_pubs_after_boot);
  // BUT the Poll path also runs doPartial after the MQTT-read block when
  // not promoting — keeps the clock fresh on Poll-heavy schedules where
  // the Poll cadence preempts the Partial cadence at resonance minutes.
  // Seed-then-draw produces 12 blits + 2 partialUpdates, same pattern as
  // a plain Partial wake.
  CHECK(s.display().bitmapBlits().size() - blits_after_boot == 12);
  CHECK(s.display().partialUpdate1BitCount() - partial_after_boot == 2);
}

TEST_CASE("Timer @ Morning :03 → Poll detects mode change → falls through to Full") {
  SIM_RESET();
  sim::Scenario s;
  s.clock().setNow(localTime(6, 30));
  coldBootInto(s, "summary");
  const int full_after_boot = s.display().fullRefreshCount();
  const auto state_pubs_after_boot =
      s.publishedMessages(fw::config::kTopicDeviceState).size();

  // HA flips active_mode to weather between cold boot and the poll.
  s.mqttPublish(fw::config::kTopicActiveMode, "weather", /*retained=*/true)
      .setRendererResponse(urlFor("weather"), fakePng());
  s.clock().setNow(localTime(6, 33));

  fw::tick(s.hal(), fw::wake::Reason::Timer);

  // Mode change detected → Full path runs.
  CHECK(s.display().fullRefreshCount() == full_after_boot + 1);
  CHECK(s.publishedMessages(fw::config::kTopicDeviceState).size() == state_pubs_after_boot + 1);
}

TEST_CASE("Timer @ Morning :15 → Full (forced-full at 15-min cadence)") {
  SIM_RESET();
  sim::Scenario s;
  s.clock().setNow(localTime(6, 30));
  coldBootInto(s, "summary");
  const int full_after_boot = s.display().fullRefreshCount();

  s.clock().setNow(localTime(6, 45));  // 405 % 15 == 0 → Full
  fw::tick(s.hal(), fw::wake::Reason::Timer);

  CHECK(s.display().fullRefreshCount() == full_after_boot + 1);
}

TEST_CASE("Timer @ Midday :05 → plain Partial (offline, no MQTT)") {
  SIM_RESET();
  sim::Scenario s;
  s.clock().setNow(localTime(10, 0));
  coldBootInto(s, "summary");
  const int full_after_boot = s.display().fullRefreshCount();
  const int partial_after_boot = s.display().partialUpdate1BitCount();
  const auto blits_after_boot = s.display().bitmapBlits().size();
  const auto state_pubs_after_boot =
      s.publishedMessages(fw::config::kTopicDeviceState).size();

  // 10:05 — plain Partial (Midday's `partial_min == 5`, `poll_min == 0`).
  // Since the PollPartial path was removed, this wake is fully offline:
  // no WiFi, no MQTT, no state/device publish. HA-driven mode changes
  // outside the active session pickup are caught only on the next Full.
  s.clock().setNow(localTime(10, 5));
  fw::tick(s.hal(), fw::wake::Reason::Timer);

  // Seed-then-draw: 12 blits, 2 partialUpdates. Cold boot's post-Full
  // cleanup set last_drawn = 10:00 so the seed step runs.
  CHECK(s.display().bitmapBlits().size() - blits_after_boot == 12);
  CHECK(s.display().partialUpdate1BitCount() - partial_after_boot == 2);
  CHECK(s.display().fullRefreshCount() == full_after_boot);
  CHECK(s.publishedMessages(fw::config::kTopicDeviceState).size() == state_pubs_after_boot);
}

TEST_CASE("Timer @ Night :07 → Skip — no network, no draw, no work") {
  SIM_RESET();
  sim::Scenario s;
  s.clock().setNow(localTime(0, 0));  // Night Full
  coldBootInto(s, "night");
  const int full_after_boot = s.display().fullRefreshCount();
  const int partial_after_boot = s.display().partialUpdate1BitCount();
  const auto blits_after_boot = s.display().bitmapBlits().size();
  const auto state_pubs_after_boot =
      s.publishedMessages(fw::config::kTopicDeviceState).size();

  // 00:07 — Night, no cadence matches → Skip.
  s.clock().setNow(localTime(0, 7));
  fw::tick(s.hal(), fw::wake::Reason::Timer);

  CHECK(s.display().fullRefreshCount() == full_after_boot);
  CHECK(s.display().partialUpdate1BitCount() == partial_after_boot);
  CHECK(s.display().bitmapBlits().size() == blits_after_boot);
  CHECK(s.publishedMessages(fw::config::kTopicDeviceState).size() == state_pubs_after_boot);
}

TEST_CASE("Timer in NowPlaying mode → Poll at every minute (override)") {
  // `optimise-now-playing-cadence` changed the override from Full-every-
  // minute to Poll-every-minute. With the same retained track on the
  // broker, a Timer wake in NowPlaying does NOT promote to Full; the Poll
  // handler reads the track topic, finds the cached hash matches, and
  // returns to sleep. Track changes are tested in
  // now_playing_track_tests.cpp.
  SIM_RESET();
  sim::Scenario s;
  s.clock().setNow(localTime(10, 0));
  s.mqttPublish(fw::config::kTopicActiveMode, "now-playing", /*retained=*/true)
      .mqttPublish(fw::config::kTopicNowPlayingTrack, "spotify:track:abc",
                   /*retained=*/true)
      .setRendererResponse(urlFor("now-playing"), fakePng());
  stubClockZone(s, "now-playing", /*x=*/48, /*y=*/73, /*font_size=*/44);
  fw::tick(s.hal(), fw::wake::Reason::ColdBoot);
  const int full_after_boot = s.display().fullRefreshCount();
  REQUIRE(full_after_boot >= 1);

  // 10:07 — in Midday this would be Skip for any other mode. With NowPlaying
  // override active, planWake returns Poll; the Poll handler checks the
  // track topic, finds the cached hash matches, no promotion.
  s.clock().setNow(localTime(10, 7));
  fw::tick(s.hal(), fw::wake::Reason::Timer);

  CHECK(s.display().fullRefreshCount() == full_after_boot);
}

TEST_CASE("Partial path falls back to Full when renderer reports no clock zone") {
  SIM_RESET();
  sim::Scenario s;
  // Cold-boot into Night WITHOUT stubbing clock-zone.json — simulates the
  // renderer's 404 response for modes with no clock-shaped DOM element.
  s.clock().setNow(localTime(0, 0));
  s.mqttPublish(fw::config::kTopicActiveMode, "night", /*retained=*/true)
      .setRendererResponse(urlFor("night"), fakePng());
  fw::tick(s.hal(), fw::wake::Reason::ColdBoot);
  // persisted.clock_zone_font_size left at 0 (404 from clock-zone fetch).
  REQUIRE(fw::wake::persisted().clock_zone_font_size == 0);
  const int full_after_boot = s.display().fullRefreshCount();

  // Move to local 06:31 — Morning Partial cadence. With no cached zone,
  // the partial path promotes to Full.
  s.clock().setNow(localTime(6, 31));
  fw::tick(s.hal(), fw::wake::Reason::Timer);

  CHECK(s.display().fullRefreshCount() == full_after_boot + 1);
  CHECK(s.display().partialUpdate1BitCount() == 0);
}

TEST_CASE("IMU tap in Morning :01 → Full (gesture path overrides Partial)") {
  SIM_RESET();
  sim::Scenario s;
  s.clock().setNow(localTime(6, 30));
  coldBootInto(s, "summary");
  const int full_after_boot = s.display().fullRefreshCount();
  const int partial_after_boot = s.display().partialUpdate1BitCount();

  s.mqttPublish(fw::config::kTopicActiveMode, "summary", /*retained=*/true)
      .setRendererResponse(urlFor("summary"), fakePng());
  s.clock().setNow(localTime(6, 31));
  s.fireTap(/*isDouble=*/false);
  fw::tick(s.hal(), fw::wake::Reason::IMU);

  // Gesture path: IMU wake → Full regardless of cadence. Pulses on this wake:
  //   - showTapAck: 3 partial pulses (force-black halo, white-with-dot, clear)
  //   - Post-Full zone cleanup: 2 partial pulses (solid-black then clean)
  // Total: 5 partialUpdate1Bit pulses.
  CHECK(s.display().fullRefreshCount() == full_after_boot + 1);
  CHECK(s.display().partialUpdate1BitCount() - partial_after_boot == 5);
  auto gestures = s.publishedMessages(fw::config::kTopicGesture);
  REQUIRE(gestures.size() == 1);
}
