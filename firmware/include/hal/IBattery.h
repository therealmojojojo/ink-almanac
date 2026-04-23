#pragma once

namespace hal {

// IBattery — fuel-gauge / ADC-based voltage readout.
//
// Contract:
//   * `readVoltage()` returns pack voltage in volts (e.g. 3.92).
//   * `readPercentage()` returns an integer 0–100.
//
// Both reads are synchronous and may block briefly (typically <20 ms). They
// should NOT be called inside hot paths; firmware reads once per wake.
class IBattery {
 public:
  virtual ~IBattery() = default;
  virtual float readVoltage() = 0;
  virtual int readPercentage() = 0;
};

}  // namespace hal
