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
                              const char* build_version,
                              bool epd_pwrgood,
                              const char* diag) {
  // 1.5 KB is enough for all fixed fields plus the ring (~900 chars max).
  char buf[1536];
  if (diag && *diag) {
    std::snprintf(
        buf, sizeof(buf),
        "{\"voltage\":%.2f,\"percentage\":%d,\"wake_reason\":\"%s\","
        "\"active_mode\":\"%s\",\"build\":\"%s\",\"epd_pwrgood\":%s,"
        "\"diag\":\"%s\"}",
        static_cast<double>(r.voltage), r.percentage,
        wake_reason ? wake_reason : "",
        active_mode ? active_mode : "",
        build_version ? build_version : "",
        epd_pwrgood ? "true" : "false",
        diag);
  } else {
    std::snprintf(
        buf, sizeof(buf),
        "{\"voltage\":%.2f,\"percentage\":%d,\"wake_reason\":\"%s\","
        "\"active_mode\":\"%s\",\"build\":\"%s\",\"epd_pwrgood\":%s}",
        static_cast<double>(r.voltage), r.percentage,
        wake_reason ? wake_reason : "",
        active_mode ? active_mode : "",
        build_version ? build_version : "",
        epd_pwrgood ? "true" : "false");
  }
  return std::string(buf);
}

}  // namespace fw::battery
