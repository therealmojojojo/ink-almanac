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

}  // namespace sim
