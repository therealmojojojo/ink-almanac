#pragma once
#ifdef ARDUINO

#include <Wire.h>

#include "config.h"
#include "hal/IIMU.h"

// LSM6DSO I²C driver. Register addresses per ST datasheet DS12140 Rev 4.
// Sensor-probe run on this unit confirmed the part is at 0x6B (SA0=VDD),
// WHO_AM_I=0x6C.

namespace fw::hal_real {

constexpr uint8_t kLSM6_ADDR        = 0x6B;
constexpr uint8_t kLSM6_WHO_AM_I    = 0x0F;
constexpr uint8_t kLSM6_CTRL1_XL    = 0x10;  // accel ODR + full-scale
constexpr uint8_t kLSM6_CTRL10_C    = 0x19;  // embedded-func / timestamp enable
constexpr uint8_t kLSM6_TAP_CFG0    = 0x56;
constexpr uint8_t kLSM6_TAP_CFG1    = 0x57;  // tap axis priority + threshold X
constexpr uint8_t kLSM6_TAP_CFG2    = 0x58;  // threshold Y + interrupts enable
constexpr uint8_t kLSM6_TAP_THS_6D  = 0x59;
constexpr uint8_t kLSM6_INT_DUR2    = 0x5A;  // single/double/quiet timing
constexpr uint8_t kLSM6_WAKE_UP_THS = 0x5B;
constexpr uint8_t kLSM6_MD1_CFG     = 0x5E;  // route events to INT1
constexpr uint8_t kLSM6_TAP_SRC     = 0x1C;
constexpr uint8_t kLSM6_OUTX_L_XL   = 0x28;
constexpr uint8_t kLSM6_WHO_AM_I_EXPECTED = 0x6C;

class RealIMU : public hal::IIMU {
 public:
  void init() override {
    Wire.begin();
    Wire.setClock(400000);

    uint8_t who = readReg(kLSM6_WHO_AM_I);
    if (who != kLSM6_WHO_AM_I_EXPECTED) {
      present_ = false;
      return;
    }
    present_ = true;

    // CTRL1_XL = 0x60 → accel ODR 416 Hz, ±2 g, LPF1 disabled.
    writeReg(kLSM6_CTRL1_XL, 0x60);
    // TAP_CFG0 (0x56): enable interrupts + tap on all three axes (0x0E) +
    // LATCHED_INT (bit 0) so tap events persist across our deep-sleep cycle
    // until TAP_SRC is read. This is what makes polling work without INT1
    // wired to the ESP32.
    writeReg(kLSM6_TAP_CFG0, 0x0E | 0x01);
    // TAP_CFG1 (0x57): X-axis threshold (bits 4:0); priority Z>Y>X set via bits 7:5 = 001.
    // Threshold is in units of FS/32; at ±2g → 1 LSB ≈ 62.5 mg. kTapThreshold from config.
    writeReg(kLSM6_TAP_CFG1, (0x01 << 5) | (fw::config::kTapThreshold & 0x1F));
    // TAP_CFG2 (0x58): Y-axis threshold + enable interrupts output.
    writeReg(kLSM6_TAP_CFG2, 0x80 | (fw::config::kTapThreshold & 0x1F));
    // TAP_THS_6D (0x59): Z-axis threshold.
    writeReg(kLSM6_TAP_THS_6D, fw::config::kTapThreshold & 0x1F);
    // INT_DUR2 (0x5A): DUR[3:0]=double-tap window, QUIET[1:0]=quiet time, SHOCK[1:0]=shock time.
    // DUR determines max time for double-tap (1 LSB = 32*ODR_XL). At 416 Hz ODR,
    // 32/416 ≈ 77 ms. kDoubleTapWindowMs/77 rounded → nibble.
    uint8_t dur = static_cast<uint8_t>(fw::config::kDoubleTapWindowMs / 77);
    if (dur > 0x0F) dur = 0x0F;
    writeReg(kLSM6_INT_DUR2, (dur << 4) | 0x03);
    // MD1_CFG (0x5E): route single-tap + double-tap interrupts to INT1.
    // bit3 = INT1_DOUBLE_TAP, bit6 = INT1_SINGLE_TAP. INT1 pad is wired on the
    // breakout but not connected to an ESP32 GPIO in the current build, so
    // this routing is latent — it will light up once an operator solders a
    // wire and enables the `ext1` wake source in firmware.
    writeReg(kLSM6_MD1_CFG, (1 << 6) | (1 << 3));
  }

  void configureTap(int /*threshold*/, int /*durationMs*/) override {
    // Hardware registers already configured from config.h in init().
    // Reserved for runtime recalibration.
  }
  void configureDoubleTap(int /*windowMs*/) override {}

  bool drainPendingTap(bool* is_double) override {
    if (!present_) return false;
    const uint8_t src = readReg(kLSM6_TAP_SRC);
    Serial.printf("[IMU] TAP_SRC=0x%02X\n", src);
    if (src == 0xFF) return false;  // read failed
    // TAP_SRC: bit 6 = TAP_IA (any tap event), bit 4 = DOUBLE_TAP, bit 5 = SINGLE_TAP.
    if (!(src & 0x40)) return false;
    if (is_double) *is_double = (src & 0x10) != 0;
    return true;
  }

 private:
  bool present_ = false;

  void writeReg(uint8_t reg, uint8_t val) {
    Wire.beginTransmission(kLSM6_ADDR);
    Wire.write(reg);
    Wire.write(val);
    Wire.endTransmission();
  }

  uint8_t readReg(uint8_t reg) {
    Wire.beginTransmission(kLSM6_ADDR);
    Wire.write(reg);
    if (Wire.endTransmission(false) != 0) return 0xFF;
    Wire.requestFrom(static_cast<int>(kLSM6_ADDR), 1);
    return Wire.available() ? Wire.read() : 0xFF;
  }
};

}  // namespace fw::hal_real

#endif  // ARDUINO
