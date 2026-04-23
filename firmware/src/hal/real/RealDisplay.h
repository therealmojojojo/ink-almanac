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

 private:
  Inkplate& panel_;
};

}  // namespace fw::hal_real

#endif  // ARDUINO
