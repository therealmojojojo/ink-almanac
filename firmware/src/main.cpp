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

int timerSecondsFor(fw::wake::Reason reason) {
  (void)reason;
  // Persisted mode guides the timer; default to 15 min if unknown.
  switch (fw::wake::persisted().current_mode) {
    case fw::modes::Mode::Summary: return fw::config::kSummaryTimerSec;
    case fw::modes::Mode::Weather: return fw::config::kWeatherTimerSec;
    case fw::modes::Mode::Gallery: return fw::config::kGalleryTimerSec;
    case fw::modes::Mode::Night:   return fw::config::kNightTimerSec;
    default:                       return fw::config::kSummaryTimerSec;
  }
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

  fw::tick(hal, reason);

  const int secs = timerSecondsFor(reason);
  Serial.printf("[fw] sleeping %d s\n", secs);
  Serial.flush();
  clock.sleepFor(secs);  // does not return
}

void loop() {
  // Unreachable — setup() ends in deep sleep.
}

#endif  // ARDUINO
