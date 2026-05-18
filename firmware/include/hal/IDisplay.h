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

  // -------------------- EPD PMIC power-good probe --------------------------
  //
  // The Soldered library's draw paths open with `if (!einkOn()) return;`
  // and `einkOn()` itself returns 0 when the TPS65186 fails to reach
  // `PWR_GOOD_OK` within 250 ms. The void-returning public draw API hides
  // that failure: `display.draw3bit()` and `partialUpdate*()` return
  // nothing, so the firmware can't tell a no-op apart from a successful
  // refresh. We probe `einkOn()` directly here so the Full path can record
  // power-good in `inkplate/state/device` and HA can alert.
  //
  // Default impl returns true (host sim and any non-Inkplate target).
  // RealDisplay delegates to `panel_.einkOn()`. Idempotent: if the panel
  // is already powered, the library returns 1 immediately.
  virtual bool ensurePanelPower() { return true; }

  // -------------------- EPD PMIC clean-down probe --------------------------
  //
  // Soldered's `TPS65186::powerDown()` (called by `einkOff()`) waits at most
  // 250 ms for the chip's PWR_GOOD register to read 0 (all rails collapsed),
  // then forces `enableRails(false)` over I2C regardless of the actual rail
  // state. If a draw cycle ends with rails still partially asserted — e.g.
  // because the decoupling caps haven't bled below the chip's PG threshold
  // in 250 ms — this creates an enable-bit / physical-rail disagreement:
  // the chip's monitors see some rails up and refuse to run the power-up
  // sequencer on the NEXT wake, even after `einkOn()` is called. The chip
  // reports PWR_GOOD = 0xA0 (partial), no fault bits set in INT1/INT2,
  // and no software sequence we tried clears it. Only physically dropping
  // VIN by removing the LiPo battery recovers it.
  //
  // See firmware/src/epd_probe.cpp for the diagnostic that established
  // the byte pattern, and openspec/changes/prevent-tps65186-partial-power
  // -wedge for the spec.
  //
  // `ensurePanelDown` calls `einkOff()` first (idempotent — no-op if the
  // chip is already off) and then polls the PMIC's PWR_GOOD register
  // directly until it reads 0x00 (rails actually drained) or `timeout_ms`
  // elapses. Returns true on clean collapse, false if rails stayed
  // partially asserted past the timeout. A `false` return is the early
  // warning that this wake just *entered* the wedge state; the caller
  // SHOULD log it and SHOULD include the raw PWR_GOOD byte in telemetry
  // so the next incident is diagnosable from HA without USB.
  //
  // 0xFF reads (bus errors or chip-off-and-non-responsive) are treated as
  // "rails down" — the chip's I2C interface goes quiet when WAKEUP is low
  // and rails are fully off, which is the desired terminal state.
  //
  // Default impl returns true (host sim, non-Inkplate targets).
  virtual bool ensurePanelDown(uint32_t timeout_ms = 3000) {
    (void)timeout_ms;
    return true;
  }

  // Raw byte read of the PMIC's PWR_GOOD register (0x0F). Used by telemetry
  // so the JSON payload published to `inkplate/state/device` carries the
  // actual per-rail status, not just the boolean returned by
  // `ensurePanelPower`. Returning 0xFA (the healthy all-rails-good value)
  // is the default for non-Inkplate targets so tests don't have to mock
  // the read explicitly to look healthy.
  virtual uint8_t readPwrGoodByte() { return 0xFA; }
};

}  // namespace hal
