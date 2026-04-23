#pragma once

#include "hal/IBattery.h"
#include "hal/IClock.h"
#include "hal/IDisplay.h"
#include "hal/IIMU.h"
#include "hal/ITransport.h"

namespace hal {

// HAL — aggregate of the five interfaces injected into the firmware main loop.
// Passed by reference; ownership lives in the bootstrap (main.cpp on device,
// Scenario on host). PIR removed in move-pir-to-ha-motion — motion detection
// lives in HA via an IKEA Zigbee/Matter sensor.
struct HAL {
  IDisplay&   display;
  IIMU&       imu;
  IBattery&   battery;
  IClock&     clock;
  ITransport& transport;
};

}  // namespace hal
