#pragma once
#ifdef ARDUINO

#include <Arduino.h>
#include <Inkplate.h>
#include <Wire.h>

#include <string>

#include "hal/IDisplay.h"

namespace fw::hal_real {

// TPS65186 I2C address and PWR_GOOD register, per the TI datasheet and
// the Soldered library's TPS65186.h. We hit the register directly rather
// than going through the library so the read is independent of any
// library-internal cached state.
inline constexpr uint8_t kTpsAddr      = 0x48;
inline constexpr uint8_t kTpsRegPwrGood = 0x0F;

class RealDisplay : public hal::IDisplay {
 public:
  explicit RealDisplay(Inkplate& panel) : panel_(panel) {}

  // Primary path: hand the URL to the library; pngle streams the HTTP response
  // straight into the panel framebuffer. This is the pattern every Soldered
  // example uses. The earlier buffer-based call matched a raw-pixel overload
  // (not PNG decode), so PNG bytes were splatted as palette values and
  // dithered to white noise.
  bool drawImageFromUrl(const std::string& url, bool full, hal::Rect rect) override {
    const bool ok = panel_.drawImage(url.c_str(),
                                     rect.x, rect.y,
                                     /*dither=*/true, /*invert=*/false);
    if (!ok) {
      Serial.printf("[RealDisplay] drawImage(url) FAILED: %s\n", url.c_str());
      return false;
    }
    if (full) panel_.display();
    else panel_.partialUpdate();
    return true;
  }

  // Retained for the fetch-failure indicator path (80×80 corner rect).
  // Not used for PNG decode — the per-pixel overload misreads PNG headers.
  void drawImage(const uint8_t* buffer,
                 std::size_t length,
                 bool full,
                 hal::Rect rect) override {
    (void)buffer; (void)length; (void)full; (void)rect;
    // Intentionally a no-op on device: the legacy buffer path never worked for
    // PNG, and the indicator glyph hasn't been implemented yet. Leaving the
    // prior face visible is better than a bogus clear.
  }

  void clear() override {
    panel_.clearDisplay();
    panel_.display();
  }

  void refresh() override { panel_.display(); }

  // -------------------- 1-bit partial-update path --------------------------
  //
  // The Soldered Inkplate library's partialUpdate() returns 0 in 3-bit mode
  // (hardware no-op). Switching to 1-bit makes it actually drive the panel,
  // so the partial path flips mode → composes glyphs → partialUpdate() →
  // flips back to 3-bit for the next full refresh.
  //
  // setDisplayMode reallocates _pBuffer / _partial inside the library, so
  // any framebuffer state in the previous mode is lost — acceptable for the
  // clock partial since each wake re-composes from baked glyphs.

  void setDisplayMode(DisplayMode mode) override {
    panel_.setDisplayMode(mode == DisplayMode::OneBit ? INKPLATE_1BIT
                                                       : INKPLATE_3BIT);
  }

  void drawBitmap1Bit(int16_t x, int16_t y,
                      const uint8_t* bitmap,
                      int16_t w, int16_t h) override {
    // Inkplate 10 (non-color variants) defines BLACK=1, WHITE=0 — see
    // InkplateLibrary defines.h. Glyph bitmaps draw ink as set bits, so we
    // need color=BLACK to get visible characters; color=0 would silently
    // write white-on-white and partialUpdate would return cycles=0.
    panel_.drawBitmap(x, y, bitmap, w, h, /*color=BLACK*/ 1);
  }

  void fillRect1Bit(int16_t x, int16_t y,
                    int16_t w, int16_t h,
                    uint8_t value) override {
    // HAL contract: value=0 means white (background), 1 means black (ink).
    // Maps directly to Inkplate's WHITE=0 / BLACK=1 in 1-bit mode.
    panel_.fillRect(x, y, w, h, value ? /*BLACK*/ 1 : /*WHITE*/ 0);
  }

  uint32_t partialUpdate1Bit() override {
    // _forced=true bypasses the library's `_blockPartial` guard, which is
    // set after every 3-bit display3b() and after begin() — without forcing
    // it, the first partial after wake degrades into a full B&W refresh and
    // returns 0. The library's own header comment flags this as the
    // "advanced use with deep sleep" path; that is exactly our use case.
    return panel_.partialUpdate(/*_forced=*/true);
  }

  bool ensurePanelPower() override {
    // panel_.einkOn() returns 1 on success, 0 if PWR_GOOD didn't latch
    // within the library's 250 ms timeout (TPS65186 fault-latched, VCOM
    // stuck, brownout, etc.). Idempotent — if the chip is already up, the
    // library returns 1 immediately without re-running the I2C config.
    return panel_.einkOn() == 1;
  }

  uint8_t readPwrGoodByte() override {
    // Direct I2C read of TPS65186 register 0x0F. Bypasses the library so
    // the value is the chip's current opinion, not a cached `_poweredUp`
    // bool. 0xFA = all five rails good (healthy). 0xA0 = the partial-power
    // wedge we diagnosed on 2026-05-17. 0xFF = chip did not ACK (likely
    // because WAKEUP is low and rails are off — telemetry treats this as
    // "down," but callers can distinguish).
    Wire.beginTransmission(kTpsAddr);
    Wire.write(kTpsRegPwrGood);
    if (Wire.endTransmission(false) != 0) return 0xFF;  // repeated start
    if (Wire.requestFrom((uint8_t)kTpsAddr, (uint8_t)1) != 1) return 0xFF;
    return Wire.available() ? Wire.read() : 0xFF;
  }

  bool ensurePanelDown(uint32_t timeout_ms = 3000) override {
    // 1) Tell the library to start its power-down sequence. einkOff() is
    //    idempotent — if rails are already off it's effectively a no-op.
    //    The library waits 250 ms internally then forces enableRails(false)
    //    even if rails haven't actually collapsed.
    panel_.einkOff();

    // 2) Poll the chip directly until rails physically drain. 50 ms
    //    cadence keeps the I2C load light; total budget = `timeout_ms`.
    //    A clean draw cycle on a healthy chip reaches 0 in 100–200 ms;
    //    we give 3 s of headroom for warm panels with slow cap discharge.
    const uint32_t start = millis();
    while ((millis() - start) < timeout_ms) {
      const uint8_t pg = readPwrGoodByte();
      // 0x00 — all rails reporting collapsed. Healthy off state.
      // 0xFF — chip did not ACK. This is the expected reading when the
      //        chip is fully powered down and WAKEUP is low; the chip's
      //        I2C interface goes quiet. Treat as "down."
      if (pg == 0x00 || pg == 0xFF) return true;
      delay(50);
    }
    // Timed out with rails still partially up. This is the wedge-entry
    // moment. The caller logs it and includes the byte in telemetry.
    return false;
  }

 private:
  Inkplate& panel_;
};

}  // namespace fw::hal_real

#endif  // ARDUINO
