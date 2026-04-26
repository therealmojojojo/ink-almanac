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

std::string urlFor(const char* mode) {
  return std::string("http://renderer.local:8575/display/") + mode + ".png";
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

TEST_CASE("timer wake with unchanged mode does partial refresh; mode change does full") {
  // Per ha/docs/architecture.md "Refresh policy": timer/fast-path wakes with
  // unchanged mode → PARTIAL refresh (clock tick advances). Only mode-changed
  // / cold-boot / post-OTA / ghost-flush conditions trigger a FULL refresh.
  // Earlier shape "skip the panel entirely on minute-tick" left the clock
  // frozen between mode transitions; this test now codifies the partial path.
  SIM_RESET();
  sim::Scenario s;
  s.clock().setNow(kApr14_0800);
  s.mqttPublish(fw::config::kTopicActiveMode, "summary", true)
      .setRendererResponse(urlFor("summary"), fakePng());
  fw::tick(s.hal(), fw::wake::Reason::ColdBoot);
  const int full_after_first = s.display().fullRefreshCount();
  const int partial_after_first = s.display().partialRefreshCount();

  // Minute-tick wake, same mode → PARTIAL refresh + state publish.
  const auto state_pubs_before = s.publishedMessages(fw::config::kTopicDeviceState).size();
  fw::tick(s.hal(), fw::wake::Reason::Timer);
  CHECK(s.display().fullRefreshCount() == full_after_first);
  CHECK(s.display().partialRefreshCount() == partial_after_first + 1);
  CHECK(s.publishedMessages(fw::config::kTopicDeviceState).size() == state_pubs_before + 1);

  // Mode change on next wake → full refresh.
  s.mqttPublish(fw::config::kTopicActiveMode, "weather", true);
  s.setRendererResponse(urlFor("weather"), fakePng());
  fw::tick(s.hal(), fw::wake::Reason::Timer);
  CHECK(s.display().fullRefreshCount() == full_after_first + 1);
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

TEST_CASE("sonos fast-path with unchanged mode partial-refreshes (clock tick)") {
  SIM_RESET();
  sim::Scenario s;
  s.clock().setNow(kApr14_0800);
  s.mqttPublish(fw::config::kTopicActiveMode, "summary", true)
      .setRendererResponse(urlFor("summary"), fakePng());
  fw::tick(s.hal(), fw::wake::Reason::ColdBoot);
  const int full_before = s.display().fullRefreshCount();
  const int partial_before = s.display().partialRefreshCount();

  // Same mode, fast-path wake → PARTIAL refresh (the clock zone updates).
  fw::tick(s.hal(), fw::wake::Reason::SonosFastPath);
  CHECK(s.display().fullRefreshCount() == full_before);
  CHECK(s.display().partialRefreshCount() == partial_before + 1);
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
  // setting active_mode = weather (single tap → weather_peek in HA).
  auto& t = s.transport();
  t.setPublishHook([&t](const sim::MockTransport::Publish& p) {
    if (p.topic == fw::config::kTopicGesture) {
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
  // Mode unchanged (still summary from the cold-boot retained value). No new
  // full refresh in this cycle; the device will catch HA's decision on the
  // next natural wake if HA publishes one later.
  CHECK(s.display().fullRefreshCount() == full_before);
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

  // Simulate HA's quiet-hours guard: gesture arrives but active_mode does NOT
  // change. (HA still acknowledges the message by re-publishing the same
  // retained value — the device's grace-window reads it and finds no change.)
  auto& t = s.transport();
  t.setPublishHook([&t](const sim::MockTransport::Publish& p) {
    if (p.topic == fw::config::kTopicGesture) {
      t.mqttPublish(fw::config::kTopicActiveMode, "night", /*retained=*/true);
    }
  });

  s.fireTap(/*isDouble=*/false);
  fw::tick(s.hal(), fw::wake::Reason::IMU);

  auto gestures = s.publishedMessages(fw::config::kTopicGesture);
  REQUIRE(gestures.size() == 1);
  // Same face — no mode change, no new full refresh.
  CHECK(s.display().fullRefreshCount() == full_before);
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
      t.mqttPublish(fw::config::kTopicActiveMode, "summary", /*retained=*/true);
    }
  });

  s.fireTap(/*isDouble=*/true);
  fw::tick(s.hal(), fw::wake::Reason::IMU);

  auto gestures = s.publishedMessages(fw::config::kTopicGesture);
  REQUIRE(gestures.size() == 1);
  CHECK(gestures[0].payload.find("double") != std::string::npos);
}
