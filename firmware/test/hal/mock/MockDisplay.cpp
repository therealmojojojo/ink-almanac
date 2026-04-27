#include "hal/mock/MockDisplay.h"

#include <cstdio>
#include <fstream>

#include "hal/mock/MockClock.h"

namespace sim {

namespace {
uint64_t fnv1a(const uint8_t* data, std::size_t n) {
  uint64_t h = 1469598103934665603ull;
  for (std::size_t i = 0; i < n; ++i) {
    h ^= data[i];
    h *= 1099511628211ull;
  }
  return h;
}
}  // namespace

MockDisplay::MockDisplay(MockClock& clock) : clock_(clock) {}

void MockDisplay::drawImage(const uint8_t* buffer,
                            std::size_t length,
                            bool full,
                            hal::Rect rect) {
  DrawCall c{};
  c.at_epoch = clock_.nowEpoch();
  c.buffer_hash = fnv1a(buffer, length);
  c.buffer_size = length;
  c.full = full;
  c.rect = rect;
  calls_.push_back(c);
  if (full) ++full_refreshes_;
  else ++partial_refreshes_;
}

void MockDisplay::clear() {
  // Treated as a full refresh of a blank field.
  DrawCall c{};
  c.at_epoch = clock_.nowEpoch();
  c.buffer_hash = 0;
  c.full = true;
  c.rect = {0, 0, 1200, 825};
  calls_.push_back(c);
  ++full_refreshes_;
}

void MockDisplay::refresh() {
  // No-op in the mock; drawImage drives the scenario.
}

bool MockDisplay::saveLastTo(const std::string& path) const {
  if (last_raw_.empty()) return false;
  std::ofstream out(path, std::ios::binary);
  if (!out) return false;
  out.write(reinterpret_cast<const char*>(last_raw_.data()),
            static_cast<std::streamsize>(last_raw_.size()));
  return out.good();
}

void MockDisplay::setLastRaw(std::vector<uint8_t> bytes) {
  last_raw_ = std::move(bytes);
}

void MockDisplay::setDisplayMode(DisplayMode mode) {
  display_mode_ = mode;
  display_mode_history_.push_back(mode);
}

void MockDisplay::drawBitmap1Bit(int16_t x, int16_t y,
                                 const uint8_t* bitmap,
                                 int16_t w, int16_t h) {
  // Hash the entire bitmap byte payload. Row stride is ceil(w/8) bytes.
  const std::size_t row_bytes = static_cast<std::size_t>((w + 7) / 8);
  const std::size_t total = row_bytes * static_cast<std::size_t>(h);
  bitmap_blits_.push_back(BitmapBlit{
      .x = x, .y = y, .w = w, .h = h,
      .bitmap_hash = bitmap ? fnv1a(bitmap, total) : 0});
}

void MockDisplay::fillRect1Bit(int16_t x, int16_t y,
                               int16_t w, int16_t h,
                               uint8_t value) {
  // Encode as a synthetic blit so tests can assert clear-before-draw ordering.
  const uint64_t pseudo_hash = (static_cast<uint64_t>(value) << 56) |
                               (static_cast<uint64_t>(static_cast<uint16_t>(w)) << 32) |
                               static_cast<uint64_t>(static_cast<uint16_t>(h));
  bitmap_blits_.push_back(BitmapBlit{
      .x = x, .y = y, .w = w, .h = h, .bitmap_hash = pseudo_hash});
}

uint32_t MockDisplay::partialUpdate1Bit() {
  ++partial_update_1bit_count_;
  return partial_update_1bit_return_;
}

}  // namespace sim
