#pragma once
#ifdef ARDUINO

#include <Arduino.h>
#include <Inkplate.h>

#include <string>

#include "hal/IDisplay.h"

namespace fw::hal_real {

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

 private:
  Inkplate& panel_;
};

}  // namespace fw::hal_real

#endif  // ARDUINO
