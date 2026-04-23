#pragma once

#include <cstddef>
#include <cstdint>
#include <vector>

namespace hal {

using Epoch = int64_t;  // seconds since Unix epoch (simulated on host).

struct Rect {
  int x, y, w, h;
};

// Wake sources the clock can arm before a deep sleep. PIR removed —
// motion now detected by the HA-side IKEA sensor (see
// openspec/changes/move-pir-to-ha-motion/).
enum class WakeSource : uint8_t {
  Timer = 1 << 0,
  IMU   = 1 << 2,
  Other = 1 << 3,
};

using WakeSourceMask = uint8_t;

inline WakeSourceMask operator|(WakeSource a, WakeSource b) {
  return static_cast<WakeSourceMask>(a) | static_cast<WakeSourceMask>(b);
}

// Compact HTTP response.
struct HttpResponse {
  int status = 0;
  std::vector<uint8_t> body;
  bool ok() const { return status >= 200 && status < 300; }
};

}  // namespace hal
