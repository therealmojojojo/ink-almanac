// Tests for the active-override MQTT mirror flow. Verifies that the device
// reads `inkplate/state/active_override` on every Full/Poll/PollPartial wake
// and updates `Persisted::session_now_playing` correctly, including the
// empty-payload short-circuit.

#include <vector>

#include "config.h"
#include "doctest.h"
#include "firmware.h"
#include "harness/Scenario.h"
#include "wake.h"

namespace {

struct ResetFirmwareState {
  ResetFirmwareState() {
    fw::wake::reset();
    fw::wake::resetScheduleForTests();
  }
};

#define SIM_RESET() ResetFirmwareState _reset_

constexpr hal::Epoch kApr14_0800 = 1'744'617'600 + 2 * 3600;
constexpr hal::Epoch localTime(int local_h, int local_m) {
  return kApr14_0800 +
         static_cast<hal::Epoch>((local_h * 60 + local_m - 11 * 60) * 60);
}
std::vector<uint8_t> fakePng() { return std::vector<uint8_t>(1024, 0x80); }
std::string urlFor(const char* mode) {
  return std::string("http://renderer.local:8575/display/") + mode + ".png";
}
void stubClockZone(sim::Scenario& s, const char* mode) {
  const std::string body =
      std::string("{\"x\":48,\"y\":73,\"w\":545,\"h\":144,\"font_size\":44}");
  std::vector<uint8_t> bytes(body.begin(), body.end());
  s.transport().setRendererResponse(
      std::string("http://renderer.local:8575/display/") + mode +
          "/clock-zone.json",
      std::move(bytes), 200);
}

}  // namespace

TEST_CASE("Active-override empty payload leaves session flag at default") {
  SIM_RESET();
  sim::Scenario s;
  s.clock().setNow(localTime(15, 0));
  s.mqttPublish(fw::config::kTopicActiveMode, "summary", /*retained=*/true)
      .setRendererResponse(urlFor("summary"), fakePng());
  stubClockZone(s, "summary");
  // No publish to kTopicActiveOverride at all → broker has nothing.

  fw::tick(s.hal(), fw::wake::Reason::ColdBoot);

  CHECK(fw::wake::persisted().session_now_playing == false);
}

TEST_CASE("Active-override 'now_playing' sets the session flag") {
  SIM_RESET();
  sim::Scenario s;
  s.clock().setNow(localTime(15, 0));
  s.mqttPublish(fw::config::kTopicActiveMode, "summary", /*retained=*/true)
      .mqttPublish(fw::config::kTopicActiveOverride, "now_playing",
                   /*retained=*/true)
      .setRendererResponse(urlFor("summary"), fakePng());
  stubClockZone(s, "summary");

  fw::tick(s.hal(), fw::wake::Reason::ColdBoot);

  CHECK(fw::wake::persisted().session_now_playing == true);
}

TEST_CASE("Active-override 'schedule' clears the session flag") {
  SIM_RESET();
  sim::Scenario s;
  s.clock().setNow(localTime(15, 0));
  // Seed the flag to true via a prior wake with now_playing override.
  s.mqttPublish(fw::config::kTopicActiveMode, "summary", /*retained=*/true)
      .mqttPublish(fw::config::kTopicActiveOverride, "now_playing",
                   /*retained=*/true)
      .setRendererResponse(urlFor("summary"), fakePng());
  stubClockZone(s, "summary");
  fw::tick(s.hal(), fw::wake::Reason::ColdBoot);
  REQUIRE(fw::wake::persisted().session_now_playing == true);

  // HA flips to schedule (linger expiry, etc.). Next Timer wake reads the
  // new value and clears the flag.
  s.mqttPublish(fw::config::kTopicActiveOverride, "schedule",
                /*retained=*/true);
  s.clock().setNow(localTime(15, 1));
  fw::tick(s.hal(), fw::wake::Reason::Timer);
  CHECK(fw::wake::persisted().session_now_playing == false);
}

TEST_CASE("Active-override unknown value is treated as 'not now_playing'") {
  // weather_peek and summary_gallery_toggle are valid HA values; the
  // device only differentiates "now_playing" from everything else.
  SIM_RESET();
  sim::Scenario s;
  s.clock().setNow(localTime(15, 0));
  s.mqttPublish(fw::config::kTopicActiveMode, "weather", /*retained=*/true)
      .mqttPublish(fw::config::kTopicActiveOverride, "weather_peek",
                   /*retained=*/true)
      .setRendererResponse(urlFor("weather"), fakePng());
  stubClockZone(s, "weather");

  fw::tick(s.hal(), fw::wake::Reason::ColdBoot);

  CHECK(fw::wake::persisted().session_now_playing == false);
}
