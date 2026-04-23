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
};

}  // namespace hal
