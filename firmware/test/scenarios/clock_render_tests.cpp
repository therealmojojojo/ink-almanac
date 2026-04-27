// Clock rasterizer tests for the per-glyph composition path. Verifies that
// fw::clock::draw():
//   - issues exactly one fillRect (zone clear) followed by 5 glyph blits;
//   - positions each glyph at cursor + glyph.left_bearing on the baseline;
//   - same time → same blits (deterministic);
//   - tabular invariant: a minute tick keeps the first 4 glyph blits
//     identical (positions and bitmap hashes) because tnum advances mean
//     '1' at column k never shifts when '4' becomes '5' in column k+1.
//   - works for both baked presets (Compact 44u and Corner 28u);
//   - does NOT call partialUpdate or change display mode.

#include <cstdint>

#include "clock_render.h"
#include "doctest.h"
#include "generated/clock_glyphs.h"
#include "hal/mock/MockClock.h"
#include "hal/mock/MockDisplay.h"

using fw::clock::draw;
using fw::clock::kCompactClock;
using fw::clock::kCornerClock;

namespace {
// fillRect + 5 glyph blits per draw.
constexpr int kBlitsPerDraw = 1 + 5;
}  // namespace

TEST_CASE("clock::draw issues fill + 5 blits at expected positions (Compact)") {
  sim::MockClock clock;
  sim::MockDisplay panel(clock);

  const int16_t zx = 100, zy = 50;
  const auto rect = draw(panel, kCompactClock, zx, zy, /*hours=*/12, /*minutes=*/34);

  const auto& blits = panel.bitmapBlits();
  REQUIRE(blits.size() == kBlitsPerDraw);

  CHECK(rect.x == zx);
  CHECK(rect.y == zy);
  CHECK(rect.w == 4 * kCompactClock.glyphs[0].advance +
                  kCompactClock.glyphs[10].advance +
                  4 * kCompactClock.letter_spacing_px);
  CHECK(rect.h == kCompactClock.line_height_px);

  CHECK(blits[0].x == zx);
  CHECK(blits[0].y == zy);
  CHECK(blits[0].w == rect.w);
  CHECK(blits[0].h == rect.h);

  // Mirror clock_render.cpp's +2 px draw-time baseline nudge.
  const auto baseline_y = static_cast<int16_t>(zy + kCompactClock.baseline_from_top_px + 2);
  const char chars[5] = {'1', '2', ':', '3', '4'};
  int16_t cursor = zx;
  for (std::size_t i = 0; i < 5; ++i) {
    const int idx = fw::clock::glyphIndex(chars[i]);
    REQUIRE(idx >= 0);
    const auto& g = kCompactClock.glyphs[static_cast<std::size_t>(idx)];
    const auto& b = blits[1u + i];
    CHECK(b.x == cursor + g.left_bearing);
    CHECK(b.y == baseline_y - g.top_bearing);
    CHECK(b.w == g.width);
    CHECK(b.h == g.height);
    cursor = static_cast<int16_t>(cursor + g.advance);
    if (i < 4) cursor = static_cast<int16_t>(cursor + kCompactClock.letter_spacing_px);
  }
}

TEST_CASE("clock::draw is deterministic — same time → same blit hashes") {
  sim::MockClock clock;
  sim::MockDisplay a(clock), b(clock);
  draw(a, kCompactClock, 0, 0, 9, 41);
  draw(b, kCompactClock, 0, 0, 9, 41);
  REQUIRE(a.bitmapBlits().size() == b.bitmapBlits().size());
  for (std::size_t i = 0; i < a.bitmapBlits().size(); ++i) {
    CHECK(a.bitmapBlits()[i].x == b.bitmapBlits()[i].x);
    CHECK(a.bitmapBlits()[i].y == b.bitmapBlits()[i].y);
    CHECK(a.bitmapBlits()[i].bitmap_hash == b.bitmapBlits()[i].bitmap_hash);
  }
}

TEST_CASE("clock::draw — minute tick keeps first 4 glyphs identical") {
  // 12:34 → 12:35: '1','2',':','3' stay; '4' → '5'. With tnum, the cursor
  // position at the start of each glyph is identical across renders, so
  // blit args for indexes 0..3 match exactly.
  sim::MockClock clock;
  sim::MockDisplay a(clock), b(clock);
  draw(a, kCompactClock, 200, 100, 12, 34);
  draw(b, kCompactClock, 200, 100, 12, 35);

  const auto& A = a.bitmapBlits();
  const auto& B = b.bitmapBlits();
  REQUIRE(A.size() == B.size());

  for (std::size_t i : {0u, 1u, 2u, 3u, 4u}) {
    INFO("blit ", i);
    CHECK(A[i].x == B[i].x);
    CHECK(A[i].y == B[i].y);
    CHECK(A[i].w == B[i].w);
    CHECK(A[i].h == B[i].h);
    CHECK(A[i].bitmap_hash == B[i].bitmap_hash);
  }
  // Last glyph differs (bitmap content; geometry can differ if '4' and '5'
  // have different bearings/heights).
  const bool geom_differs = A[5u].x != B[5u].x || A[5u].y != B[5u].y ||
                            A[5u].w != B[5u].w || A[5u].h != B[5u].h;
  CHECK((A[5u].bitmap_hash != B[5u].bitmap_hash || geom_differs));
}

TEST_CASE("clock::draw — Corner preset (gv-split / np / gallery-text)") {
  sim::MockClock clock;
  sim::MockDisplay panel(clock);

  draw(panel, kCornerClock, 0, 0, 18, 47);
  const auto& blits = panel.bitmapBlits();
  REQUIRE(blits.size() == kBlitsPerDraw);
  const int expected_w =
      4 * kCornerClock.glyphs[0].advance + kCornerClock.glyphs[10].advance;
  CHECK(blits[0].w == expected_w);
  CHECK(blits[0].h == kCornerClock.line_height_px);
}

TEST_CASE("clock::draw — out-of-range hours/minutes wrap via modulo") {
  sim::MockClock clock;
  sim::MockDisplay a(clock), b(clock);
  draw(a, kCompactClock, 0, 0, 12, 34);
  draw(b, kCompactClock, 0, 0, /*hours=*/12 + 24, /*minutes=*/34 + 60);
  REQUIRE(a.bitmapBlits().size() == b.bitmapBlits().size());
  for (std::size_t i = 0; i < a.bitmapBlits().size(); ++i) {
    CHECK(a.bitmapBlits()[i].bitmap_hash == b.bitmapBlits()[i].bitmap_hash);
  }
}

TEST_CASE("clock::draw — does NOT call partialUpdate or change display mode") {
  sim::MockClock clock;
  sim::MockDisplay panel(clock);
  draw(panel, kCompactClock, 0, 0, 0, 0);
  CHECK(panel.partialUpdate1BitCount() == 0);
  CHECK(panel.displayModeHistory().empty());
}

TEST_CASE("clock::draw — every minute of a day produces 6 blits") {
  sim::MockClock clock;
  for (int h = 0; h < 24; ++h) {
    for (int m = 0; m < 60; ++m) {
      sim::MockDisplay panel(clock);
      const auto rect = draw(panel, kCompactClock, 10, 10, h, m);
      CHECK(rect.w > 0);
      CHECK(rect.h > 0);
      CHECK(panel.bitmapBlits().size() == kBlitsPerDraw);
    }
  }
}
