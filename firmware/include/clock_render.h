#pragma once

#include <cstdint>

#include "generated/clock_glyphs.h"
#include "hal/IDisplay.h"

namespace fw::clock {

// Rectangle that draw() actually painted.
struct DrawnRect {
  int16_t x;
  int16_t y;
  int16_t w;
  int16_t h;
};

// Compose "HH:MM" from baked Fraunces glyphs into the panel's 1-bit
// framebuffer at (zone_x, zone_y). One fillRect over the zone (clears any
// stale pixels in the partial-update diff window), then five glyph blits at
// `cursor + glyph.left_bearing`. Cursor advances by `glyph.advance +
// preset.letter_spacing_px` after each glyph.
//
// Hours 0..23, minutes 0..59 (out-of-range values wrap via modulo).
//
// Does NOT set display mode or call partialUpdate — caller's responsibility.
DrawnRect draw(hal::IDisplay& panel,
               const Preset& preset,
               int16_t zone_x,
               int16_t zone_y,
               int hours,
               int minutes);

// Width in pixels of "HH:MM" rendered with `preset`. tnum guarantees all
// digits share `preset.glyphs[0].advance`; colon has its own advance.
int zoneWidthPx(const Preset& preset);

// Height in pixels of the clock zone — preset.line_height_px.
int zoneHeightPx(const Preset& preset);

}  // namespace fw::clock
