#include "doctest.h"
#include "harness/Scenario.h"

// Worked example: verify the Scenario harness advances time and scripts
// IMU events cleanly. PIR removed with the HA-motion migration; this test
// now uses an IMU tap as the scripted gesture.

TEST_CASE("scenario — harness plumbing for a Summary cycle") {
  sim::Scenario s;
  s.clock().setNow(1'744'617'600);  // 2025-04-14 06:00 UTC
  s.setBattery(95)
      .setRendererResponse(
          "http://renderer.local:8575/display/summary.png",
          std::vector<uint8_t>(500, 0x80))
      .advanceTo(1'744'617'600 + 30 * 60)  // +30 min
      .fireTap()
      .advanceBy(30);

  CHECK(s.now() == 1'744'617'600 + 30 * 60 + 30);
}
