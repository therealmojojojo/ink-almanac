#pragma once
#ifdef ARDUINO

#include <Wire.h>
#include <esp_sleep.h>

#include "config.h"
#include "hal/IIMU.h"

// LSM6DSO I²C driver. Register addresses per ST datasheet DS12140 Rev 4.
// Sensor-probe run on this unit confirmed the part is at 0x6B (SA0=VDD),
// WHO_AM_I=0x6C.

namespace fw::hal_real {

constexpr uint8_t kLSM6_ADDR        = 0x6B;
constexpr uint8_t kLSM6_WHO_AM_I    = 0x0F;
constexpr uint8_t kLSM6_CTRL1_XL    = 0x10;  // accel ODR + full-scale
constexpr uint8_t kLSM6_CTRL3_C     = 0x12;  // INT1 polarity + drive (PP_OD, H_LACTIVE)
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

    // CRITICAL: snapshot TAP_SRC *before* any other register writes. Re-writing
    // CTRL1_XL (or other config) restarts the accelerometer pipeline and clears
    // the chip's tap-event latch, so by the time drainPendingTap() runs later
    // in the tick the bits are gone. This read also un-latches INT1, letting it
    // return to high-Z so R41 can restore the idle HIGH on IO36.
    pending_tap_src_ = readReg(kLSM6_TAP_SRC);
    Serial.printf("[IMU] init: cached TAP_SRC=0x%02X\n", pending_tap_src_);

    // CTRL3_C = 0x34 → IF_INC | PP_OD | H_LACTIVE. INT1 must be open-drain
    // active-low because IO36 is shared with the SW3 wake-button net (R41
    // pulls high; INT1 sinks LOW on tap, matching the button's electrical
    // behavior). Without this the line would fight R41 and the device would
    // not wake reliably. See firmware/docs/gestures.md "Wiring".
    writeReg(kLSM6_CTRL3_C, 0x34);
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
    // INT_DUR2 (0x5A): DUR[3:0]=double-tap window, QUIET[1:0]=quiet time after
    // first tap (during which a second impulse is ignored), SHOCK[1:0]=max
    // shock duration. QUIET is at max (3 → ~29 ms at 416 Hz ODR) so a finger
    // rebound from a single tap is absorbed into the same event rather than
    // registering as a second tap and triggering DOUBLE_TAP. SHOCK=3 (max
    // ~58 ms) gives the impulse plenty of time. DUR derived from
    // kDoubleTapWindowMs (1 LSB = 32 * 1/ODR_XL ≈ 77 ms at 416 Hz).
    uint8_t dur = static_cast<uint8_t>(fw::config::kDoubleTapWindowMs / 77);
    if (dur > 0x0F) dur = 0x0F;
    writeReg(kLSM6_INT_DUR2, (dur << 4) | (3 << 2) | 3);
    // WAKE_UP_THS (0x5B) bit 7 (SINGLE_DOUBLE_TAP) = 1 → enable double-tap
    // recognition alongside single-tap. Without this the chip only fires
    // single-tap events.
    writeReg(kLSM6_WAKE_UP_THS, 0x80);
    // MD1_CFG (0x5E): route single-tap + double-tap interrupts to INT1.
    // bit3 = INT1_DOUBLE_TAP, bit6 = INT1_SINGLE_TAP.
    writeReg(kLSM6_MD1_CFG, (1 << 6) | (1 << 3));

    // Arm the ext0 wake source: INT1 → IO36 (shared with SW3 wake-button net).
    // LOW level wakes the ESP32; same call the official Inkplate 10 wake-button
    // example uses, so a button press still works as a redundant trigger.
    esp_sleep_enable_ext0_wakeup(static_cast<gpio_num_t>(fw::config::kImuWakeGpio),
                                 0 /* level LOW */);
  }

  void configureTap(int /*threshold*/, int /*durationMs*/) override {
    // Hardware registers already configured from config.h in init().
    // Reserved for runtime recalibration.
  }
  void configureDoubleTap(int /*windowMs*/) override {}

  bool drainPendingTap(bool* is_double) override {
    if (!present_) return false;
    // Returns the snapshot taken in init(), then consumes it so a second call
    // in the same wake cycle reports no event.
    const uint8_t src = pending_tap_src_;
    pending_tap_src_ = 0;
    Serial.printf("[IMU] drain: TAP_SRC=0x%02X\n", src);
    if (src == 0xFF || src == 0x00) return false;  // read failed or no event
    // TAP_SRC bit 5 = SINGLE_TAP, bit 4 = DOUBLE_TAP. (bit 6 TAP_IA is only
    // asserted while INT1 is high and self-clears, so we can't rely on it
    // surviving until the post-wake read.)
    if (!(src & 0x30)) return false;
    if (is_double) *is_double = (src & 0x10) != 0;
    return true;
  }

 private:
  bool present_ = false;
  uint8_t pending_tap_src_ = 0;

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
