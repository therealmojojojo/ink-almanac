#pragma once

#include <cstdint>
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
// `epd_pg_raw` is the raw PWR_GOOD register byte (0xFA healthy, 0xA0 the
// partial-power wedge, 0xFF chip not responding). Carried alongside the
// bool so HA can distinguish "chip wedged at 0xA0" from "chip not even
// ACKing" without needing USB serial. See
// openspec/changes/prevent-tps65186-partial-power-wedge.
//
// `epd_down_clean` is true if the previous draw cycle ended with rails
// fully collapsed (PWR_GOOD reached 0 within the ensurePanelDown timeout),
// false if it timed out with rails still partially up — i.e. the wedge
// was *just entered* and the next wake will probably see einkOn fail.
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
                              const char* schedule_hash = nullptr,
                              uint8_t epd_pg_raw = 0xFA,
                              bool epd_down_clean = true);

}  // namespace fw::battery
