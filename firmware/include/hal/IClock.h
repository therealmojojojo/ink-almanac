#pragma once

#include "hal/types.h"

namespace hal {

// IClock — time + deep-sleep abstraction.
//
// Contract:
//   * `nowEpoch()` returns the current wall time in seconds since epoch.
//     On-device: populated via NTP during boot (or held by RTC across sleeps).
//     On-host (mock): simulated time under the harness's control.
//   * `sleepFor(seconds)` enters deep sleep for the requested duration, then
//     the system resumes from boot (ESP32 semantics). On the host, the mock
//     advances simulated time and returns without wrapping; scenarios model
//     the boot-on-wake behavior explicitly.
//   * `scheduleWake(mask)` ORs the given wake sources into the active
//     configuration. Call IIMU-configured INT pins separately; this method
//     handles the clock timer only. (PIR removed with the HA-motion
//     migration — see openspec/changes/move-pir-to-ha-motion/.)
//
// Lifecycle:
//   No init required. The ESP32 implementation uses the RTC peripheral
//   directly; the mock uses monotonic counters.
class IClock {
 public:
  virtual ~IClock() = default;
  virtual Epoch nowEpoch() const = 0;
  virtual void sleepFor(int seconds) = 0;
  virtual void scheduleWake(WakeSourceMask mask) = 0;
};

}  // namespace hal
