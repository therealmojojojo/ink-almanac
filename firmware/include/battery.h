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
std::string toDeviceStateJson(Reading r,
                              const char* wake_reason,
                              const char* active_mode,
                              const char* build_version);

}  // namespace fw::battery
