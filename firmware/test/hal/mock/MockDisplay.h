#pragma once

#include <cstdint>
#include <optional>
#include <vector>

#include "hal/IDisplay.h"
#include "hal/types.h"

namespace sim {

class MockClock;  // forward decl

class MockDisplay : public hal::IDisplay {
 public:
  struct DrawCall {
    hal::Epoch at_epoch;
    uint64_t buffer_hash;
    std::size_t buffer_size;
    bool full;
    hal::Rect rect;
  };

  explicit MockDisplay(MockClock& clock);

  void drawImage(const uint8_t* buffer,
                 std::size_t length,
                 bool full,
                 hal::Rect rect) override;
  void clear() override;
  void refresh() override;

  // 1-bit partial path (used by the clock-tick wake type — see
  // firmware/src/clock_render.cpp and main_loop.cpp partial path).
  void setDisplayMode(DisplayMode mode) override;
  void drawBitmap1Bit(int16_t x, int16_t y,
                      const uint8_t* bitmap,
                      int16_t w, int16_t h) override;
  void fillRect1Bit(int16_t x, int16_t y,
                    int16_t w, int16_t h,
                    uint8_t value) override;
  uint32_t partialUpdate1Bit() override;

  struct BitmapBlit {
    int16_t x, y, w, h;
    uint64_t bitmap_hash;
  };

  // Query API (test-facing)
  const std::vector<DrawCall>& calls() const { return calls_; }
  int fullRefreshCount() const { return full_refreshes_; }
  int partialRefreshCount() const { return partial_refreshes_; }
  std::optional<uint64_t> lastBufferHash() const {
    return calls_.empty() ? std::nullopt
                          : std::optional<uint64_t>{calls_.back().buffer_hash};
  }

  // 1-bit query API
  DisplayMode displayMode() const { return display_mode_; }
  const std::vector<DisplayMode>& displayModeHistory() const { return display_mode_history_; }
  const std::vector<BitmapBlit>& bitmapBlits() const { return bitmap_blits_; }
  int partialUpdate1BitCount() const { return partial_update_1bit_count_; }
  // Set the cycle count returned by partialUpdate1Bit() so a test can
  // simulate "partial actually drove the panel" (cycles > 0) vs "library
  // refused" (cycles == 0).
  void setPartialUpdate1BitReturn(uint32_t cycles) { partial_update_1bit_return_ = cycles; }

  // Saves the last received buffer to disk for visual inspection (dry-run mode).
  bool saveLastTo(const std::string& path) const;
  // Stores the raw last buffer internally (dry-run uses this to retain the PNG).
  void setLastRaw(std::vector<uint8_t> bytes);

 private:
  MockClock& clock_;
  std::vector<DrawCall> calls_;
  std::vector<uint8_t> last_raw_;
  int full_refreshes_ = 0;
  int partial_refreshes_ = 0;

  // 1-bit partial path state
  DisplayMode display_mode_ = DisplayMode::ThreeBit;
  std::vector<DisplayMode> display_mode_history_;
  std::vector<BitmapBlit> bitmap_blits_;
  int partial_update_1bit_count_ = 0;
  uint32_t partial_update_1bit_return_ = 1;  // default: pretend the call drove the panel
};

}  // namespace sim
