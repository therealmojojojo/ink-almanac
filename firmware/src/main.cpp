// On-device entry point. Builds only for Arduino/ESP32. The host simulator
// never links this file; its entry is firmware/test/main.cpp.

#ifdef ARDUINO

#include <Arduino.h>
#include <Inkplate.h>

#include "config.h"
#include "firmware.h"
#include "hal/HAL.h"
#include "modes.h"
#include "hal/real/RealBattery.h"
#include "hal/real/RealClock.h"
#include "hal/real/RealDisplay.h"
#include "hal/real/RealIMU.h"
#include "hal/real/RealTransport.h"
#include "wake.h"

namespace {

fw::wake::Reason detectWakeReason() {
  switch (esp_sleep_get_wakeup_cause()) {
    case ESP_SLEEP_WAKEUP_TIMER: return fw::wake::Reason::Timer;
    case ESP_SLEEP_WAKEUP_EXT0:  return fw::wake::Reason::IMU;
    default:                     return fw::wake::Reason::ColdBoot;
  }
}

// Sleep until the next non-Skip wake on the schedule planner. Aligns to the
// next minute boundary minus seconds-into-current-minute and tick-elapsed,
// clamped to a sane lower bound so we never spin on a tight loop if planning
// math somehow underflows.
int plannedSleepSec(uint32_t tick_start_unix, uint32_t tick_end_unix) {
  const uint32_t local_now =
      tick_end_unix + static_cast<uint32_t>(fw::config::kTzOffsetSec);
  const int local_min_of_day = static_cast<int>((local_now / 60u) % 1440u);
  const int seconds_into_minute = static_cast<int>(local_now % 60u);
  const auto plan = fw::wake::planWake(local_min_of_day, fw::wake::persisted().current_mode);
  // tick_elapsed = how many seconds the wake itself burned; subtract so the
  // next wake lands on the wall-clock minute, not 60 s after the present one.
  const int tick_elapsed = static_cast<int>(tick_end_unix - tick_start_unix);
  int s = plan.minutes_to_next_wake * 60 - seconds_into_minute - tick_elapsed;
  if (s < 5) s = 5;     // never sleep less than 5 s — guard against loops
  if (s > 3600) s = 3600;  // never sleep more than 1 h — guard against bad RTC
  return s;
}

}  // namespace

Inkplate panel(INKPLATE_3BIT);

void setup() {
  Serial.begin(115200);
  delay(200);
  Serial.println();
  Serial.println("[fw] boot");

  panel.begin();

  // Instantiate real HAL wrappers. Lifetimes are the rest of setup() — we
  // never return from clock.sleepFor() below, so stack residency is fine.
  fw::hal_real::RealDisplay   display{panel};
  fw::hal_real::RealIMU       imu;
  fw::hal_real::RealBattery   battery{panel};
  fw::hal_real::RealClock     clock;
  fw::hal_real::RealTransport transport;

  imu.init();

  hal::HAL hal{display, imu, battery, clock, transport};
  const fw::wake::Reason reason = detectWakeReason();
  Serial.printf("[fw] wake reason=%d\n", static_cast<int>(reason));

  const uint32_t tick_start = static_cast<uint32_t>(clock.nowEpoch());
  fw::tick(hal, reason);
  const uint32_t tick_end = static_cast<uint32_t>(clock.nowEpoch());

  const int secs = plannedSleepSec(tick_start, tick_end);
  Serial.printf("[fw] sleeping %d s (path-aligned)\n", secs);
  Serial.flush();
  clock.sleepFor(secs);  // does not return
}

void loop() {
  // Unreachable — setup() ends in deep sleep.
}

#endif  // ARDUINO
