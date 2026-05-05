// Track-change detection in NowPlaying mode. Exercises the Poll handler's
// hash-based promotion-to-Full when `inkplate/state/now_playing_track`
// changes, and verifies the empty-payload short-circuit + session-override
// gating that keep the device from doing wasted Fulls.

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
  ResetFirmwareState() {
    fw::wake::reset();
    fw::wake::resetScheduleForTests();
  }
};

#define SIM_RESET() ResetFirmwareState _reset_

constexpr hal::Epoch kApr14_0800 = 1'744'617'600 + 2 * 3600;  // 08:00 UTC = 11:00 local

constexpr hal::Epoch localTime(int local_h, int local_m) {
  return kApr14_0800 +
         static_cast<hal::Epoch>((local_h * 60 + local_m - 11 * 60) * 60);
}

std::vector<uint8_t> fakePng(std::size_t n = 1024, uint8_t fill = 0x80) {
  return std::vector<uint8_t>(n, fill);
}

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

// Bring the device up in NowPlaying mode with an initial track. After
// this helper, persisted.current_mode == NowPlaying, sonos_track_hash is
// populated for "track-1", and the renderer is stubbed for follow-up
// pulls.
void enterNowPlayingWithTrack(sim::Scenario& s, const char* track_id) {
  s.mqttPublish(fw::config::kTopicActiveMode, "now-playing", /*retained=*/true)
      .mqttPublish(fw::config::kTopicNowPlayingTrack, track_id, /*retained=*/true)
      .mqttPublish(fw::config::kTopicActiveOverride, "now_playing", /*retained=*/true)
      .setRendererResponse(urlFor("now-playing"), fakePng());
  stubClockZone(s, "now-playing");
  fw::tick(s.hal(), fw::wake::Reason::ColdBoot);
}

}  // namespace

TEST_CASE("NowPlaying same-track Poll does not promote to Full") {
  SIM_RESET();
  sim::Scenario s;
  s.clock().setNow(localTime(15, 0));
  enterNowPlayingWithTrack(s, "spotify:track:abc");

  // Cold-boot Full has happened. fullRefreshCount == 1.
  REQUIRE(s.display().fullRefreshCount() == 1);
  REQUIRE(fw::wake::persisted().sonos_track_hash != 0u);
  const uint32_t hash_before = fw::wake::persisted().sonos_track_hash;

  // Next minute Timer wake: same track on the broker → Poll, no promotion.
  s.clock().setNow(localTime(15, 1));
  fw::tick(s.hal(), fw::wake::Reason::Timer);
  CHECK(s.display().fullRefreshCount() == 1);
  CHECK(fw::wake::persisted().sonos_track_hash == hash_before);
}

TEST_CASE("NowPlaying track-change Poll promotes to Full and updates cache") {
  SIM_RESET();
  sim::Scenario s;
  s.clock().setNow(localTime(15, 0));
  enterNowPlayingWithTrack(s, "spotify:track:abc");

  REQUIRE(s.display().fullRefreshCount() == 1);
  const uint32_t hash_before = fw::wake::persisted().sonos_track_hash;

  // Operator (or HA) publishes a new track to the retained topic.
  s.mqttPublish(fw::config::kTopicNowPlayingTrack, "spotify:track:xyz",
                /*retained=*/true);

  // Next minute Timer wake: hash mismatch → promote to Full.
  s.clock().setNow(localTime(15, 1));
  fw::tick(s.hal(), fw::wake::Reason::Timer);

  CHECK(s.display().fullRefreshCount() == 2);
  CHECK(fw::wake::persisted().sonos_track_hash != hash_before);
}

TEST_CASE("NowPlaying empty track payload short-circuits") {
  SIM_RESET();
  sim::Scenario s;
  s.clock().setNow(localTime(15, 0));
  // Active mode is now-playing, override flag is set, but the broker has
  // no retained value at all on the track topic — simulates Sonos having
  // never played in HA's lifetime, or an explicit clear.
  s.mqttPublish(fw::config::kTopicActiveMode, "now-playing", /*retained=*/true)
      .mqttPublish(fw::config::kTopicActiveOverride, "now_playing", /*retained=*/true)
      .setRendererResponse(urlFor("now-playing"), fakePng());
  stubClockZone(s, "now-playing");
  fw::tick(s.hal(), fw::wake::Reason::ColdBoot);

  // Cold-boot Full happened, but the doFull track-cache update sees an
  // empty payload and leaves sonos_track_hash at 0.
  REQUIRE(s.display().fullRefreshCount() == 1);
  CHECK(fw::wake::persisted().sonos_track_hash == 0u);

  // Next minute Poll: empty payload short-circuit, no promotion, hash unchanged.
  s.clock().setNow(localTime(15, 1));
  fw::tick(s.hal(), fw::wake::Reason::Timer);
  CHECK(s.display().fullRefreshCount() == 1);
  CHECK(fw::wake::persisted().sonos_track_hash == 0u);
}

TEST_CASE("Track change during a peek does not promote") {
  SIM_RESET();
  sim::Scenario s;
  s.clock().setNow(localTime(15, 0));
  enterNowPlayingWithTrack(s, "spotify:track:abc");
  REQUIRE(s.display().fullRefreshCount() == 1);

  // Simulate HA's tap-peek: active_mode flips to summary, override stays
  // now_playing. The renderer for summary needs to be stubbed for the
  // peek-Full to succeed.
  s.mqttPublish(fw::config::kTopicActiveMode, "summary", /*retained=*/true)
      .setRendererResponse(urlFor("summary"), fakePng());
  stubClockZone(s, "summary");

  // Next Timer wake: mode-change-promotion fires (active mode moved to
  // Summary), draws Summary. fullRefreshCount becomes 2.
  s.clock().setNow(localTime(15, 1));
  fw::tick(s.hal(), fw::wake::Reason::Timer);
  REQUIRE(s.display().fullRefreshCount() == 2);
  REQUIRE(static_cast<int>(fw::wake::persisted().current_mode) ==
          static_cast<int>(fw::modes::Mode::Summary));

  // Now a track change arrives on the broker WHILE we're peeking at
  // Summary. The session is still now_playing so the planner returns
  // Poll, but the Poll handler's track-check is gated on
  // resolved == NowPlaying — Summary is the resolved active_mode here,
  // so the track check is skipped. No promotion.
  s.mqttPublish(fw::config::kTopicNowPlayingTrack, "spotify:track:xyz",
                /*retained=*/true);
  s.clock().setNow(localTime(15, 2));
  fw::tick(s.hal(), fw::wake::Reason::Timer);
  CHECK(s.display().fullRefreshCount() == 2);  // unchanged — no promotion during peek
}
