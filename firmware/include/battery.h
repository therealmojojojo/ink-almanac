#pragma once

#include <string>

#include "hal/HAL.h"

namespace fw::battery {

struct Reading {
  float voltage;
  int percentage;
};

Reading read(hal::IBattery& b);

// JSON payload suitable for publishing to `inkplate/state/device`.
//
// `epd_pwrgood` is the result of the most recent `IDisplay::ensurePanelPower`
// probe (see add-epd-power-good-diagnostic). On full-cycle wakes this is
// the live PMIC power-good state; HA reads it as a binary_sensor with
// `device_class: problem` and alerts when the panel is wedged.
//
// `diag` is the rendered fw::diag ring (compact text, ~900 chars max). nullable.
//
// `wifi_rssi` is the device's just-measured WiFi signal in dBm (0 means
// not connected). Surfaced in HA so the operator can see link quality
// alongside battery / wake_reason without external tools.
//
// `schedule_hash` is the FNV-32 hash of the JSON payload that produced the
// current cached wake schedule, formatted as 8 lowercase hex digits. When
// the cache is invalid (cold-boot pre-MQTT, baked default in effect)
// callers pass "00000000". HA mirrors this against its expected-hash
// template sensor to confirm the device adopted the latest schedule.
std::string toDeviceStateJson(Reading r,
                              const char* wake_reason,
                              const char* active_mode,
                              const char* build_version,
                              bool epd_pwrgood,
                              int wifi_rssi,
                              const char* diag = nullptr,
                              const char* schedule_hash = nullptr);

}  // namespace fw::battery
