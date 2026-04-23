#include "harness/Scenario.h"

namespace sim {

Scenario::Scenario()
    : display_(clock_), imu_(clock_), battery_(clock_, 100) {
  clock_.onTick([this](int seconds, bool asleep) {
    battery_.onTick(seconds, asleep);
  });
  // Baseline current-draw parameters (mA). These are placeholders that will
  // be refined once hardware measurements exist. See firmware/docs/power-model.md.
  battery_.setCurrentMa("deep_sleep", 0.15f);      // ~150 µA standby
  battery_.setCurrentMa("active_summary", 90.0f);  // WiFi + render + panel refresh
  battery_.setCurrentMa("active_weather", 90.0f);
  battery_.setCurrentMa("active_gallery", 90.0f);
  battery_.setCurrentMa("active_night", 85.0f);
  battery_.setCurrentMa("active_now_playing", 90.0f);
  battery_.setCurrentMa("wifi_connect", 140.0f);   // WiFi association burst
  battery_.setCurrentMa("ha_command_wake", 75.0f); // HA-driven short render
}

Scenario::~Scenario() = default;

Scenario& Scenario::advanceBy(int seconds) {
  clock_.advanceBy(seconds);
  return *this;
}

Scenario& Scenario::advanceTo(hal::Epoch target) {
  clock_.advanceTo(target);
  return *this;
}

Scenario& Scenario::fireTap(bool isDouble) {
  imu_.scriptTap(clock_.nowEpoch(), isDouble);
  return *this;
}

Scenario& Scenario::setBattery(int percentage) {
  battery_.reset(percentage);
  return *this;
}

Scenario& Scenario::mqttPublish(const std::string& topic,
                                const std::string& payload,
                                bool retained) {
  transport_.mqttPublish(topic, payload, retained);
  return *this;
}

Scenario& Scenario::setRendererResponse(const std::string& url,
                                        std::vector<uint8_t> png,
                                        int status) {
  transport_.setRendererResponse(url, std::move(png), status);
  return *this;
}

Scenario& Scenario::setWifiOnline(bool b) {
  transport_.setWifiOnline(b);
  return *this;
}

Scenario& Scenario::setMqttOnline(bool b) {
  transport_.setMqttOnline(b);
  return *this;
}

}  // namespace sim
