#include "battery.h"

#include <cstdio>
#include <sstream>

namespace fw::battery {

Reading read(hal::IBattery& b) {
  return {b.readVoltage(), b.readPercentage()};
}

std::string toDeviceStateJson(Reading r,
                              const char* wake_reason,
                              const char* active_mode,
                              const char* build_version) {
  char buf[256];
  std::snprintf(
      buf, sizeof(buf),
      "{\"voltage\":%.2f,\"percentage\":%d,\"wake_reason\":\"%s\","
      "\"active_mode\":\"%s\",\"build\":\"%s\"}",
      static_cast<double>(r.voltage), r.percentage,
      wake_reason ? wake_reason : "",
      active_mode ? active_mode : "",
      build_version ? build_version : "");
  return std::string(buf);
}

}  // namespace fw::battery
