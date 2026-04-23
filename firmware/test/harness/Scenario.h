#pragma once

#include <cstdint>
#include <memory>
#include <string>
#include <vector>

#include "hal/HAL.h"
#include "hal/mock/MockBattery.h"
#include "hal/mock/MockClock.h"
#include "hal/mock/MockDisplay.h"
#include "hal/mock/MockIMU.h"
#include "hal/mock/MockTransport.h"

namespace sim {

// Scenario — fluent API for writing timeline-driven simulator tests.
//
// Typical use:
//   Scenario s;
//   s.setBattery(95)
//    .setRendererResponse("http://localhost:8575/display/summary.png", {...})
//    .advanceTo(parseEpoch("2026-04-14T08:00:00Z"))
//    .fireTap()
//    .advanceBy(5);
//   REQUIRE(s.display().fullRefreshCount() == 1);
//
// PIR removed in move-pir-to-ha-motion — motion is now HA-driven via the
// IKEA Zigbee/Matter sensor and arrives as a `Reason::HACommand` wake.
class Scenario {
 public:
  Scenario();
  ~Scenario();

  // --- Time control --------------------------------------------------------
  Scenario& advanceBy(int seconds);
  Scenario& advanceTo(hal::Epoch target);
  hal::Epoch now() const { return clock_.nowEpoch(); }

  // --- Sensor injection ----------------------------------------------------
  Scenario& fireTap(bool isDouble = false);
  Scenario& setBattery(int percentage);

  // --- Network control -----------------------------------------------------
  Scenario& mqttPublish(const std::string& topic,
                        const std::string& payload,
                        bool retained = true);
  Scenario& setRendererResponse(const std::string& url,
                                std::vector<uint8_t> png,
                                int status = 200);
  Scenario& setWifiOnline(bool b);
  Scenario& setMqttOnline(bool b);

  // --- Query API -----------------------------------------------------------
  const MockDisplay& display() const { return display_; }
  const MockIMU& imu() const { return imu_; }
  MockBattery& battery() { return battery_; }
  const MockBattery& battery() const { return battery_; }
  MockClock& clock() { return clock_; }
  const MockClock& clock() const { return clock_; }
  MockTransport& transport() { return transport_; }
  const MockTransport& transport() const { return transport_; }

  int batteryPercentage() { return battery_.readPercentage(); }
  int partialRefreshCount() const { return display_.partialRefreshCount(); }
  int fullRefreshCount() const { return display_.fullRefreshCount(); }
  hal::WakeSourceMask wakeSourcesArmed() const {
    return clock_.scheduledWakeMask();
  }
  std::vector<MockTransport::Publish> publishedMessages(
      const std::string& topic) const {
    return transport_.publishesOn(topic);
  }

  // HAL bundle to pass into the firmware main loop.
  hal::HAL hal() { return {display_, imu_, battery_, clock_, transport_}; }

 private:
  MockClock clock_;
  MockDisplay display_;
  MockIMU imu_;
  MockBattery battery_;
  MockTransport transport_;
};

// Convenience assertions that read naturally in tests.
#define SIM_REQUIRE_LAST_MODE(s, expected_hash) \
  do { \
    auto h = (s).display().lastBufferHash(); \
    REQUIRE(h.has_value()); \
    REQUIRE(*h == (expected_hash)); \
  } while (0)

#define SIM_REQUIRE_BATTERY_AT_LEAST(s, min_pct) \
  do { \
    REQUIRE((s).batteryPercentage() >= (min_pct)); \
  } while (0)

}  // namespace sim
