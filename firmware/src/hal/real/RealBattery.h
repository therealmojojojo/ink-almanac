#pragma once
#ifdef ARDUINO

#include <Inkplate.h>

#include "hal/IBattery.h"

namespace fw::hal_real {

class RealBattery : public hal::IBattery {
 public:
  explicit RealBattery(Inkplate& p) : panel_(p) {}

  float readVoltage() override { return panel_.readBattery(); }
  int readPercentage() override {
    // Approximate LiPo curve: 3.3V=0%, 4.15V=100%, linear in between.
    float v = readVoltage();
    int p = static_cast<int>((v - 3.3f) / (4.15f - 3.3f) * 100.0f);
    if (p < 0) p = 0;
    if (p > 100) p = 100;
    return p;
  }

 private:
  Inkplate& panel_;
};

}  // namespace fw::hal_real

#endif  // ARDUINO
