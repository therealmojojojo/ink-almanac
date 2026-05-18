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
                              int wifi_rssi,
                              const char* diag,
                              const char* schedule_hash,
                              uint8_t epd_pg_raw,
                              bool epd_down_clean) {
  // 1.5 KB is enough for all fixed fields plus the ring (~900 chars max).
  char buf[1536];
  const char* sched = (schedule_hash && *schedule_hash) ? schedule_hash : "00000000";
  if (diag && *diag) {
    std::snprintf(
        buf, sizeof(buf),
        "{\"voltage\":%.2f,\"percentage\":%d,\"wake_reason\":\"%s\","
        "\"active_mode\":\"%s\",\"build\":\"%s\",\"epd_pwrgood\":%s,"
        "\"epd_pg_raw\":\"0x%02X\",\"epd_down_clean\":%s,"
        "\"wifi_rssi\":%d,\"schedule_hash\":\"%s\",\"diag\":\"%s\"}",
        static_cast<double>(r.voltage), r.percentage,
        wake_reason ? wake_reason : "",
        active_mode ? active_mode : "",
        build_version ? build_version : "",
        epd_pwrgood ? "true" : "false",
        static_cast<unsigned>(epd_pg_raw),
        epd_down_clean ? "true" : "false",
        wifi_rssi,
        sched,
        diag);
  } else {
    std::snprintf(
        buf, sizeof(buf),
        "{\"voltage\":%.2f,\"percentage\":%d,\"wake_reason\":\"%s\","
        "\"active_mode\":\"%s\",\"build\":\"%s\",\"epd_pwrgood\":%s,"
        "\"epd_pg_raw\":\"0x%02X\",\"epd_down_clean\":%s,"
        "\"wifi_rssi\":%d,\"schedule_hash\":\"%s\"}",
        static_cast<double>(r.voltage), r.percentage,
        wake_reason ? wake_reason : "",
        active_mode ? active_mode : "",
        build_version ? build_version : "",
        epd_pwrgood ? "true" : "false",
        static_cast<unsigned>(epd_pg_raw),
        epd_down_clean ? "true" : "false",
        wifi_rssi,
        sched);
  }
  return std::string(buf);
}

}  // namespace fw::battery
