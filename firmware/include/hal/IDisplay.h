#pragma once

#include <cstddef>
#include <cstdint>
#include <string>

#include "hal/types.h"

namespace hal {

// IDisplay — e-paper panel abstraction.
//
// Two draw paths, one winning at a time:
//
//   * `drawImageFromUrl(url, ...)` — library-native fetch + PNG decode + blit.
//     Device implementation calls the Inkplate library's URL-based drawImage
//     which streams the response through pngle directly into the framebuffer.
//     Default impl returns `false` so callers (sim) fall back to the buffer
//     path; real hardware overrides.
//
//   * `drawImage(buffer, ...)` — pre-decoded raw-pixel buffer, used by the
//     simulator (scenarios inject synthetic bytes) and by the fetch-failure
//     indicator path.
//
// `full=true` triggers a full refresh (clears ghosting, ≥1.5 s); `full=false`
// is a partial refresh (fast, accumulates ghosting). `rect` specifies the
// region touched; ignored when `full=true`.
//
// Lifecycle: constructed once at boot. No init/teardown hooks; the
// implementation owns panel bring-up internally.
class IDisplay {
 public:
  virtual ~IDisplay() = default;
  virtual bool drawImageFromUrl(const std::string& url, bool full, Rect rect) {
    (void)url; (void)full; (void)rect;
    return false;
  }
  virtual void drawImage(const uint8_t* buffer,
                         std::size_t length,
                         bool full,
                         Rect rect) = 0;
  virtual void clear() = 0;
  virtual void refresh() = 0;

  // -------------------- 1-bit partial-update path --------------------------
  //
  // Used by the offline minute-tick wakes that compose the clock zone from
  // baked Fraunces glyphs and call partialUpdate() in 1-bit mode (the only
  // mode where the Soldered Inkplate library actually drives a partial
  // waveform on Inkplate 10 — 3-bit partialUpdate is a hardware no-op).
  //
  // Real implementation forwards to panel.setDisplayMode + panel.drawBitmap +
  // panel.partialUpdate. Default (host) implementations are no-ops returning
  // 0, overridden by MockDisplay for scenario tests.
  enum class DisplayMode { ThreeBit, OneBit };

  virtual void setDisplayMode(DisplayMode /*mode*/) {}

  // 1-bit bitmap blit at (x, y) into the active framebuffer. Bitmap layout:
  // 1bpp, MSB-first within byte, row-padded to byte boundary
  // (i.e. ceil(w/8) bytes per row). Set bits draw black; cleared bits leave
  // the destination pixel untouched (transparent), matching Adafruit GFX
  // drawBitmap with a single foreground color.
  virtual void drawBitmap1Bit(int16_t /*x*/, int16_t /*y*/,
                              const uint8_t* /*bitmap*/,
                              int16_t /*w*/, int16_t /*h*/) {}

  // Fill a 1-bit rect with `value` (0 = white, 1 = black). Used to blank the
  // clock zone before drawing the next minute's digits.
  virtual void fillRect1Bit(int16_t /*x*/, int16_t /*y*/,
                            int16_t /*w*/, int16_t /*h*/,
                            uint8_t /*value*/) {}

  // Push the 1-bit framebuffer to the panel via partialUpdate(). Returns the
  // library's reported cycle count — > 0 means the panel was actually
  // driven; 0 means the call was a no-op (hardware refused, e.g. wrong mode).
  // Tests assert the > 0 case to prove the partial actually fired.
  virtual uint32_t partialUpdate1Bit() { return 0; }
};

}  // namespace hal
