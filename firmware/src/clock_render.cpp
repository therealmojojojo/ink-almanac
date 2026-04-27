#include "clock_render.h"

namespace fw::clock {

namespace {
constexpr int kStringLen = 5;  // "HH:MM"
}  // namespace

int zoneWidthPx(const Preset& preset) {
  // 4 digits at tnum advance + 1 colon + 4 letter-spacings between glyphs.
  return 4 * preset.glyphs[0].advance + preset.glyphs[10].advance +
         4 * preset.letter_spacing_px;
}

int zoneHeightPx(const Preset& preset) {
  return preset.line_height_px;
}

DrawnRect draw(hal::IDisplay& panel,
               const Preset& preset,
               int16_t zone_x,
               int16_t zone_y,
               int hours,
               int minutes) {
  if (hours < 0 || hours > 23) hours = ((hours % 24) + 24) % 24;
  if (minutes < 0 || minutes > 59) minutes = ((minutes % 60) + 60) % 60;

  char buf[kStringLen];
  buf[0] = static_cast<char>('0' + (hours / 10));
  buf[1] = static_cast<char>('0' + (hours % 10));
  buf[2] = ':';
  buf[3] = static_cast<char>('0' + (minutes / 10));
  buf[4] = static_cast<char>('0' + (minutes % 10));

  const auto total_w = static_cast<int16_t>(zoneWidthPx(preset));
  const auto total_h = static_cast<int16_t>(zoneHeightPx(preset));

  // White-out the zone so the partial diff against any prior framebuffer is
  // bounded. value=0 → white (Inkplate BLACK=1, WHITE=0).
  panel.fillRect1Bit(zone_x, zone_y, total_w, total_h, /*value=*/0);

  // +2 px nudge: the bake's measured baseline is consistently 2 px above
  // where the live renderer's pipeline lands the same baseline on the
  // panel. Probably accumulated sub-pixel rounding between the isolated
  // bake page and the live face's surrounding layout context. Easier to
  // correct at draw time than to chase the source.
  const auto baseline_y = static_cast<int16_t>(zone_y + preset.baseline_from_top_px + 2);
  int16_t cursor = zone_x;
  for (int i = 0; i < kStringLen; ++i) {
    const int idx = glyphIndex(buf[i]);
    if (idx < 0) continue;
    const auto& g = preset.glyphs[idx];
    const auto draw_x = static_cast<int16_t>(cursor + g.left_bearing);
    const auto draw_y = static_cast<int16_t>(baseline_y - g.top_bearing);
    panel.drawBitmap1Bit(draw_x, draw_y,
                         preset.bitmap_data + g.bitmap_offset,
                         static_cast<int16_t>(g.width),
                         static_cast<int16_t>(g.height));
    cursor = static_cast<int16_t>(cursor + g.advance);
    if (i < kStringLen - 1) {
      cursor = static_cast<int16_t>(cursor + preset.letter_spacing_px);
    }
  }

  return DrawnRect{zone_x, zone_y, total_w, total_h};
}

}  // namespace fw::clock
