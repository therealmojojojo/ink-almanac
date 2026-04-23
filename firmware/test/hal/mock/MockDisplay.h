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

  // Query API (test-facing)
  const std::vector<DrawCall>& calls() const { return calls_; }
  int fullRefreshCount() const { return full_refreshes_; }
  int partialRefreshCount() const { return partial_refreshes_; }
  std::optional<uint64_t> lastBufferHash() const {
    return calls_.empty() ? std::nullopt
                          : std::optional<uint64_t>{calls_.back().buffer_hash};
  }

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
};

}  // namespace sim
