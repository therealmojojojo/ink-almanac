// Firmware main tick — wakes up, decides the wake path from the schedule
// planner (Full / Poll / Partial / PollPartial / Skip), executes that path,
// publishes device state where appropriate, and arms the next wake.
//
// Pure logic over the HAL interfaces so the same code runs on-device (with
// real wrappers) and in the host simulator. The schedule planner lives in
// fw::wake::planWake() (firmware/src/wake.cpp); the on-device clock
// rasterizer lives in fw::clock (clock_render.cpp + generated/clock_glyphs.*).

#include "firmware.h"

#include <cstring>
#include <ctime>
#include <optional>
#include <string>

#include "battery.h"
#include "clock_render.h"
#include "config.h"
#include "diag.h"
#include "gestures.h"
#include "modes.h"
#include "wake.h"

#ifdef ARDUINO
#include <Arduino.h>
#include "secrets.h"  // INKPLATE_RENDERER_BASE on device; host sim injects via Scenario.
#define FW_LOG(fmt, ...) Serial.printf("[tick] " fmt "\n", ##__VA_ARGS__)
#else
#define FW_LOG(fmt, ...) ((void)0)
#endif

namespace fw {

namespace {

// ---------- helpers ---------------------------------------------------------

int hourOfDay(hal::Epoch local_now) {
  std::time_t t = static_cast<std::time_t>(local_now);
  std::tm* gm = std::gmtime(&t);
  return gm ? gm->tm_hour : 0;
}

int minuteOfDay(hal::Epoch local_now) {
  std::time_t t = static_cast<std::time_t>(local_now);
  std::tm* gm = std::gmtime(&t);
  if (!gm) return 0;
  return gm->tm_hour * 60 + gm->tm_min;
}

fw::modes::Mode timeOfDayFallback(int hour) {
  if (hour >= 6 && hour < 10) return fw::modes::Mode::Summary;
  if (hour >= 10 && hour < 22) return fw::modes::Mode::Weather;
  return fw::modes::Mode::Night;
}

std::string trim(std::string s) {
  while (!s.empty() && (s.back() == '\n' || s.back() == '\r' || s.back() == ' '))
    s.pop_back();
  std::size_t i = 0;
  while (i < s.size() && (s[i] == '\n' || s[i] == '\r' || s[i] == ' ')) ++i;
  return s.substr(i);
}

// Very small quoted-string extractor: finds `"key":"value"` in a JSON blob.
std::string pickString(const std::string& json, const char* key) {
  std::string needle = std::string("\"") + key + "\":\"";
  auto pos = json.find(needle);
  if (pos == std::string::npos) return {};
  pos += needle.size();
  auto end = json.find('"', pos);
  return end == std::string::npos ? std::string{} : json.substr(pos, end - pos);
}

// Sibling: `"key": <int>` → int. Returns `default_` if the key is missing,
// no digits follow, or parsing overflows int.
int pickInt(const std::string& json, const char* key, int default_) {
  std::string needle = std::string("\"") + key + "\":";
  auto pos = json.find(needle);
  if (pos == std::string::npos) return default_;
  pos += needle.size();
  while (pos < json.size() && (json[pos] == ' ' || json[pos] == '\t')) ++pos;
  int sign = 1;
  if (pos < json.size() && json[pos] == '-') { sign = -1; ++pos; }
  long long v = 0;
  bool any = false;
  while (pos < json.size() && json[pos] >= '0' && json[pos] <= '9') {
    v = v * 10 + (json[pos] - '0');
    ++pos;
    any = true;
    if (v > 1'000'000'000LL) return default_;
  }
  return any ? static_cast<int>(sign * v) : default_;
}

fw::modes::Mode parseModePayload(const std::string& payload) {
  std::string as_json = pickString(payload, "mode");
  std::string candidate = trim(as_json.empty() ? payload : as_json);
  return fw::modes::parse(candidate);
}

fw::modes::Mode resolveActiveMode(hal::ITransport& mqtt, int hour) {
  auto payload = mqtt.mqttReadRetained(fw::config::kTopicActiveMode);
  if (!payload.empty()) {
    auto m = parseModePayload(payload);
    if (m != fw::modes::Mode::Unknown) return m;
  }
  return timeOfDayFallback(hour);
}

std::string rendererBase() {
#if defined(INKPLATE_RENDERER_BASE)
  return INKPLATE_RENDERER_BASE;
#else
  return "http://renderer.local:8575";
#endif
}

std::string rendererUrl(fw::modes::Mode m) {
  return rendererBase() + "/display/" + fw::modes::toString(m) + ".png";
}

std::string clockZoneUrl(fw::modes::Mode m) {
  return rendererBase() + "/display/" + fw::modes::toString(m) + "/clock-zone.json";
}

// Portable short blocking sleep — Arduino's delay() blocks the main task
// for `ms` milliseconds. On the host simulator the body compiles to a no-op
// (tests assert blits/partialUpdate counts, not real-time pacing).
inline void msleepShort(int ms) {
#ifdef ARDUINO
  delay(ms);
#else
  (void)ms;
#endif
}

// === Notifications zone =====================================================
//
// Reserved area in the top-right corner of every face for transient,
// device-driven indicators painted via 1-bit partial updates outside the
// renderer's Full-refresh pipeline. Today the only notification is the
// tap-acknowledgment glyph below; future candidates include a WiFi/HTTP
// error mark, an OTA-in-progress indicator, or a low-battery warning that
// flashes ahead of the chrome battery dropping below threshold.
//
// Slot geometry. The renderer's `.battery-indicator` sits at top:14u
// right:22u (~x=1115..1180, y=14..32). Notifications anchor in or just
// left of that slot at fixed pixel coordinates. The slot is *reserved*
// across all faces — even where the chrome battery isn't drawn (Night) or
// is occluded by a full-bleed image (gallery-visual landscape variants),
// nothing else competes for those pixels. So notifications use the same
// coordinates everywhere; on faces with a visible battery they read as
// "next to the battery", on the others they read as "a small mark in the
// device's status zone". We accept the latter ambiguity because every
// notification is paired with a Full that follows within 5-10 s, replacing
// the transient mark with full chrome before the user has time to wonder.
//
// Common shape contract for any notification added here:
//   - 1-bit partial-update path; never trigger a Full from the notification
//   - Self-clearing within ~1-2 s (so it doesn't bleed into the next Full)
//   - Anchored within the slot so it overlaps no other element on any face
//   - Begin with a force-black pulse (see below) to guarantee the
//     subsequent white pulse drives the panel even when DMemoryNew is
//     already white
//
// The 1-bit pulses leave a small zone in inconsistent state vs the prior
// 3-bit Full's gray pixels, but the next Full naturally repaints over it.
// ============================================================================

// Tap-acknowledgment glyph. On every IMU wake with a confirmed tap, paint
// 1 black dot (single tap) or 2 black dots (double tap) on a small white
// halo, anchored in the notifications zone (see above). Three partial
// pulses:
//
//   1. Solid black over the halo region. Forces DMemoryNew to black so the
//      next white pulse actually drives the panel — without this, "writing
//      white" is a no-op when DMemoryNew is already white, and the halo
//      stays invisible against a dark gallery image.
//   2. White halo with black dot(s). Halo pixels diff black→white → pulse
//      white. Dot pixels diff black→black → no pulse → stay black.
//   3. (After the 700 ms hold) Solid white over the halo region. Halo
//      pixels are white→white no-op; dot pixels diff black→white → pulse
//      white → dots clear.
//
// Three ~250 ms partial pulses + a 700 ms hold = ack visible for ~700-900 ms,
// total ~1.5 s added to the wake cost, ~0.18 mAh per tap (3 × 0.06).
//
// Why a halo: gallery faces draw a full-bleed image that covers the
// top-right corner. Without the halo the dots are unreadable over dark
// portions of the image. The halo guarantees readability regardless of
// what the underlying face has painted there.
//
// Halo at x=1068..1100, y=18..34 lands just left of the battery slot on
// every face without overlapping the indicator where it's drawn.
void showTapAck(hal::IDisplay& panel, fw::gestures::TapKind kind) {
  if (kind == fw::gestures::TapKind::None) return;

  constexpr int16_t kDotSize  = 8;
  // Position calibrated against the live panel 2026-04-27: the original
  // (1080, 22) target landed 15 px right and 4 px high of the operator-
  // intended slot. Shifted to (1065, 26).
  constexpr int16_t kDotY     = 26;
  constexpr int16_t kSingleX  = 1065;
  constexpr int16_t kDoubleX0 = 1057;
  constexpr int16_t kDoubleX1 = 1075;
  // Halo region (also the rect used to force-black, force-white, and clear).
  // Dimensioned to surround either single- or double-dot layout with a few
  // px of margin so the halo reads as a deliberate badge, not as a tight
  // box around the dots.
  constexpr int16_t kHaloX    = 1053;
  constexpr int16_t kHaloY    = 22;
  constexpr int16_t kHaloW    = 32;
  constexpr int16_t kHaloH    = 16;

  panel.setDisplayMode(hal::IDisplay::DisplayMode::OneBit);

  // Pulse 1 — force halo region to known black. Briefly visible black
  // square; the next pulse swaps it to white-with-dots almost immediately.
  panel.fillRect1Bit(kHaloX, kHaloY, kHaloW, kHaloH, /*value=*/1);
  panel.partialUpdate1Bit();

  // Pulse 2 — white halo + black dot(s). White halo pixels diff
  // black→white → pulse white. Dot pixels remain black (no diff).
  panel.fillRect1Bit(kHaloX, kHaloY, kHaloW, kHaloH, /*value=*/0);
  if (kind == fw::gestures::TapKind::Single) {
    panel.fillRect1Bit(kSingleX, kDotY, kDotSize, kDotSize, /*value=*/1);
  } else {
    panel.fillRect1Bit(kDoubleX0, kDotY, kDotSize, kDotSize, /*value=*/1);
    panel.fillRect1Bit(kDoubleX1, kDotY, kDotSize, kDotSize, /*value=*/1);
  }
  panel.partialUpdate1Bit();

  msleepShort(700);

  // Pulse 3 — clear back to white. Dots diff black→white → pulse white;
  // halo is white→white no-op.
  panel.fillRect1Bit(kHaloX, kHaloY, kHaloW, kHaloH, /*value=*/0);
  panel.partialUpdate1Bit();

  panel.setDisplayMode(hal::IDisplay::DisplayMode::ThreeBit);
}

// Map a renderer-reported font_size to the firmware's baked Preset. Returns
// nullptr when no preset matches — caller falls back to Full so the missing
// preset shows up as a visible "wrong cadence" rather than a wrong-shape draw.
const fw::clock::Preset* presetByFontSize(uint16_t font_size) {
  if (font_size == fw::clock::kSummaryClock.font_size_px) return &fw::clock::kSummaryClock;
  if (font_size == fw::clock::kCompactClock.font_size_px) return &fw::clock::kCompactClock;
  if (font_size == fw::clock::kCornerClock.font_size_px) return &fw::clock::kCornerClock;
  return nullptr;
}

// Fetch the active mode's clock zone from the renderer and cache it in
// Persisted RTC RAM. Called after every successful Full draw. On 404 / parse
// failure the firmware leaves the previous zone in place — Partial wakes
// will then either still draw correctly (if the layout didn't move) or fall
// through to Full when the cached preset doesn't match a baked one.
void fetchAndStoreClockZone(hal::ITransport& t, fw::modes::Mode mode) {
  auto resp = t.httpGet(clockZoneUrl(mode));
  if (!resp.ok() || resp.body.empty()) {
    FW_LOG("clock-zone fetch failed status=%d", resp.status);
    // Mark zone unknown so Partial promotes to Full until we get a fresh one.
    wake::persisted().clock_zone_font_size = 0;
    return;
  }
  const std::string body(resp.body.begin(), resp.body.end());
  const int x = pickInt(body, "x", -1);
  const int y = pickInt(body, "y", -1);
  const int fs = pickInt(body, "font_size", -1);
  if (x < 0 || y < 0 || fs <= 0) {
    FW_LOG("clock-zone parse failed body='%s'", body.c_str());
    wake::persisted().clock_zone_font_size = 0;
    return;
  }
  wake::persisted().clock_zone_x = static_cast<int16_t>(x);
  wake::persisted().clock_zone_y = static_cast<int16_t>(y);
  wake::persisted().clock_zone_font_size = static_cast<uint16_t>(fs);
  FW_LOG("clock-zone stored x=%d y=%d fs=%d", x, y, fs);
}

bool backoffFetch(hal::ITransport& t,
                  const std::string& url,
                  hal::HttpResponse* out) {
  for (int i = 0; i < fw::config::kRendererMaxRetries; ++i) {
    auto r = t.httpGet(url);
    if (r.ok() && !r.body.empty()) {
      *out = std::move(r);
      return true;
    }
    (void)fw::config::kRendererBackoffSec;
  }
  return false;
}

// ---------- partial-path helper --------------------------------------------

// Compose the clock zone from baked Fraunces glyphs, push via partialUpdate.
// Returns true if the partial actually drove the panel. False means we
// don't have a usable zone for the current mode (cold boot before any Full
// landed, renderer reports no clock element, or the renderer's font_size
// has no matching baked Preset) — caller falls back to Full.
//
// Two partialUpdate calls per wake to defeat the "ghost from previous
// minute" problem that arises because PSRAM is zeroed on every deep-sleep
// wake (so the library's DMemoryNew "previous frame" buffer can't naturally
// seed itself):
//
//   1. Seed: draw the previously-drawn digits into `_partial`, partialUpdate
//      with DMemoryNew=0 → library pulses white-to-black on those pixels
//      (visually a no-op — they're already black on the panel from the
//      prior full or partial). Library memcpys DMemoryNew := old pattern.
//
//   2. Draw: clear `_partial` (fillRect inside `clock::draw`), draw new
//      digits, partialUpdate with DMemoryNew=old, _partial=new → diff has
//      both directions → cleans old-only pixels to white AND draws
//      new-only pixels to black in a single waveform cycle.
//
// On cold boot or after a mode change, last_drawn is 0xff and step 1 is
// skipped — first partial after a Full smudges, but only that first one;
// the Full path also runs a one-shot seed (see doFull) so even that case
// is clean as long as the renderer published a zone.
bool doPartial(hal::HAL& h, hal::Epoch local_now, fw::diag::Entry* diag = nullptr) {
  const auto& p = wake::persisted();
  if (p.clock_zone_font_size == 0) {
    FW_LOG("partial skipped (no zone cached for mode=%s)",
           fw::modes::toString(p.current_mode));
    return false;
  }
  const auto* preset = presetByFontSize(p.clock_zone_font_size);
  if (!preset) {
    FW_LOG("partial skipped (no preset for font_size=%u, mode=%s)",
           static_cast<unsigned>(p.clock_zone_font_size),
           fw::modes::toString(p.current_mode));
    return false;
  }
  std::time_t t = static_cast<std::time_t>(local_now);
  std::tm* gm = std::gmtime(&t);
  if (!gm) return false;

  h.display.setDisplayMode(hal::IDisplay::DisplayMode::OneBit);

  // Step 1 — seed DMemoryNew with the previously-drawn digit pattern.
  // Skipped on cold boot when last_drawn is the 0xff sentinel.
  if (p.last_drawn_hh != 0xff && p.last_drawn_mm != 0xff) {
    fw::clock::draw(h.display, *preset, p.clock_zone_x, p.clock_zone_y,
                    p.last_drawn_hh, p.last_drawn_mm);
    h.display.partialUpdate1Bit();
  }

  // Step 2 — draw new digits; partialUpdate diff cleans old + draws new.
  fw::clock::draw(h.display, *preset, p.clock_zone_x, p.clock_zone_y,
                  gm->tm_hour, gm->tm_min);
  const uint32_t cycles = h.display.partialUpdate1Bit();
  h.display.setDisplayMode(hal::IDisplay::DisplayMode::ThreeBit);

  wake::persisted().last_drawn_hh = static_cast<uint8_t>(gm->tm_hour);
  wake::persisted().last_drawn_mm = static_cast<uint8_t>(gm->tm_min);

  FW_LOG("partial mode=%s %02d:%02d at (%d,%d) fs=%u cycles=%u",
         fw::modes::toString(p.current_mode), gm->tm_hour, gm->tm_min,
         p.clock_zone_x, p.clock_zone_y,
         static_cast<unsigned>(p.clock_zone_font_size),
         static_cast<unsigned>(cycles));

  if (diag) {
    diag->cycles = static_cast<uint16_t>(cycles > 0xFFFF ? 0xFFFF : cycles);
    if (cycles > 0) diag->flags |= 0x10;  // partial_succeeded
  }
  return true;
}

// ---------- full-path helper (original tick body, lightly factored) --------

void doFull(hal::HAL& h,
            wake::Reason reason,
            fw::gestures::TapKind tap,
            int local_hour,
            hal::Epoch local_now,
            bool wifi,
            bool mqtt,
            // If the caller (Poll/PollPartial) already decoded a mode payload
            // and decided to escalate, pass it here so we don't re-fetch.
            std::optional<fw::modes::Mode> already_resolved,
            fw::diag::Entry* diag = nullptr) {
  bool gesture_published = false;
  fw::modes::Mode active = wake::persisted().current_mode;

  if (reason == wake::Reason::IMU && tap != fw::gestures::TapKind::None && mqtt) {
    const char* kind = tap == fw::gestures::TapKind::Double ? "double" : "single";
    h.transport.mqttPublish(
        fw::config::kTopicGesture,
        std::string("{\"kind\":\"") + kind + "\"}",
        /*retained=*/false);
    gesture_published = true;
    FW_LOG("gesture published (%s); grace window %d ms", kind,
           fw::config::kGestureGraceMs);

    auto payload = h.transport.mqttWaitForMessage(
        fw::config::kTopicActiveMode, fw::config::kGestureGraceMs);
    if (!payload.empty()) {
      auto m = parseModePayload(payload);
      if (m != fw::modes::Mode::Unknown) active = m;
    }
  } else if (already_resolved.has_value() &&
             *already_resolved != fw::modes::Mode::Unknown) {
    active = *already_resolved;
  } else if (mqtt) {
    active = resolveActiveMode(h.transport, local_hour);
  }
  if (active == fw::modes::Mode::Unknown) active = timeOfDayFallback(local_hour);

  [[maybe_unused]] const bool mode_changed = active != wake::persisted().current_mode;
  FW_LOG("mode=%s changed=%d", fw::modes::toString(active), mode_changed ? 1 : 0);

  // EPD power-good probe (see add-epd-power-good-diagnostic). Soldered's
  // library silently bails any draw call when `einkOn()` returns 0
  // (TPS65186 fault-latched, VCOM stuck, brownout). The void-returning
  // public API hides that, leaving the panel showing whatever it had
  // last drawn while the firmware reports MQTT state cheerfully. We probe
  // here so the failure becomes a `false` boolean in `state/device`.
  const bool epd_pwrgood = h.display.ensurePanelPower();
  FW_LOG("epd_pwrgood=%d", epd_pwrgood ? 1 : 0);
  if (diag) {
    if (wifi)         diag->flags |= 0x01;
    if (mqtt)         diag->flags |= 0x02;
    if (epd_pwrgood)  diag->flags |= 0x04;
  }

  // Draw the active face. URL path on device; buffer-fallback in sim.
  // Skip entirely when the PMIC failed to power up — the library would
  // silently no-op anyway, and we save the network round-trip.
  bool draw_succeeded = false;
  if (wifi && epd_pwrgood) {
    const auto url = rendererUrl(active);
    const bool full = true;  // 3-bit Inkplate 10 — partial in 3-bit is a no-op.
    const hal::Rect full_rect{0, 0, 1200, 825};
    FW_LOG("draw full=%d url=%s", full ? 1 : 0, url.c_str());

    const bool drawn_from_url = h.display.drawImageFromUrl(url, full, full_rect);
    if (drawn_from_url) {
      FW_LOG("drew (url path)%s", "");
      draw_succeeded = true;
    } else {
      hal::HttpResponse resp;
      if (backoffFetch(h.transport, url, &resp)) {
        FW_LOG("resp status=%d len=%u (buffer path)", resp.status, (unsigned)resp.body.size());
        h.display.drawImage(resp.body.data(), resp.body.size(), full, full_rect);
        FW_LOG("drew (buffer path)%s", "");
        draw_succeeded = true;
      } else {
        FW_LOG("fetch FAILED%s", "");
        // Unavailable indicator — 80×80 corner box.
        uint8_t empty[1] = {0};
        h.display.drawImage(empty, 1, /*full=*/false, hal::Rect{1100, 720, 80, 80});
      }
    }
  }

  if (draw_succeeded) {
    wake::persisted().current_mode = active;
    wake::persisted().partial_refresh_count = 0;
    // Refresh the clock-zone cache for the just-drawn mode. Done after
    // the e-ink update so the visible refresh isn't blocked by this fetch.
    if (wifi) fetchAndStoreClockZone(h.transport, active);

    // Post-Full zone cleanup. The Full draws at 3-bit grayscale, so digits
    // have anti-aliased gray edges around the solid-black centers. The 1-bit
    // partial path's diff can only "see" black-vs-white at the digit ink
    // positions; it never pulses the AA gray pixels just outside, so they
    // ghost as the minute changes. Fix: pulse the zone solid black, then
    // pulse it white-with-digits. The first pulse forces the panel and
    // DMemoryNew to a known 1-bit state (gray AA gets overwritten); the
    // second cleans the zone to white where the new digits aren't.
    // Subsequent partial wakes diff against last_drawn (set here to the
    // current minute) and produce ghost-free updates until the next Full.
    const auto* preset = presetByFontSize(wake::persisted().clock_zone_font_size);
    if (preset) {
      std::time_t t = static_cast<std::time_t>(local_now);
      std::tm* gm = std::gmtime(&t);
      if (gm) {
        const int16_t zx = wake::persisted().clock_zone_x;
        const int16_t zy = wake::persisted().clock_zone_y;
        const auto zw = static_cast<int16_t>(fw::clock::zoneWidthPx(*preset));
        const auto zh = static_cast<int16_t>(fw::clock::zoneHeightPx(*preset));

        h.display.setDisplayMode(hal::IDisplay::DisplayMode::OneBit);
        // Pulse 1: solid black over zone.
        h.display.fillRect1Bit(zx, zy, zw, zh, /*value=*/1);
        h.display.partialUpdate1Bit();
        // Pulse 2: white background + new digits black.
        fw::clock::draw(h.display, *preset, zx, zy, gm->tm_hour, gm->tm_min);
        h.display.partialUpdate1Bit();
        h.display.setDisplayMode(hal::IDisplay::DisplayMode::ThreeBit);

        wake::persisted().last_drawn_hh = static_cast<uint8_t>(gm->tm_hour);
        wake::persisted().last_drawn_mm = static_cast<uint8_t>(gm->tm_min);
      } else {
        wake::persisted().last_drawn_hh = 0xff;
        wake::persisted().last_drawn_mm = 0xff;
      }
    } else {
      // No baked preset for this mode (e.g. Summary at 160u). Reset
      // last_drawn so any future partial path skips the seed step.
      wake::persisted().last_drawn_hh = 0xff;
      wake::persisted().last_drawn_mm = 0xff;
    }
  }

  if (diag && draw_succeeded) diag->flags |= 0x08;

  if (mqtt) {
    auto reading = fw::battery::read(h.battery);
    // Diag-ring snapshot: rendered into a stack buffer so the JSON builder
    // can splice it inline without owning storage. The size is sized to
    // hold the ring header + 32 entries at ~25 chars each.
    char diag_buf[1024];
    if (diag) fw::diag::record(*diag);
    fw::diag::format(diag_buf, sizeof(diag_buf));
    auto json = fw::battery::toDeviceStateJson(
        reading, wake::toString(reason), fw::modes::toString(active),
        fw::kBuildVersion, epd_pwrgood, diag_buf);
    h.transport.mqttPublish(fw::config::kTopicDeviceState, json, /*retained=*/true);

    if (reason == wake::Reason::IMU && tap != fw::gestures::TapKind::None &&
        !gesture_published) {
      const char* kind = tap == fw::gestures::TapKind::Double ? "double" : "single";
      h.transport.mqttPublish(
          fw::config::kTopicGesture,
          std::string("{\"kind\":\"") + kind + "\"}",
          /*retained=*/false);
    }
  }
}

}  // namespace

// ---------- tick orchestrator ----------------------------------------------

void tick(hal::HAL h, wake::Reason reason) {
  const auto now = h.clock.nowEpoch();
  const auto local_now = static_cast<hal::Epoch>(
      static_cast<long long>(now) + fw::config::kTzOffsetSec);
  const int local_hour = hourOfDay(local_now);
  const int local_min_of_day = minuteOfDay(local_now);

  // Per-wake diagnostic entry. Populated as we go; recorded into the RTC
  // ring on every return path so the next Full's MQTT publish carries the
  // ring back to HA. The doFull path records itself (right before the JSON
  // build); other paths record explicitly via `record_diag`.
  fw::diag::Entry e{};
  e.epoch = static_cast<uint32_t>(now);
  e.path = 0xff;  // "not planned yet"; doFull/doPartial paths overwrite below
  bool diag_recorded = false;
  auto record_diag = [&]() {
    if (!diag_recorded) { fw::diag::record(e); diag_recorded = true; }
  };

  // Latched-tap polling — Timer wake might mask a pending IMU event because
  // INT1 isn't ext1-wired but TAP_SRC is latched across deep sleep.
  fw::gestures::TapKind polled_tap = fw::gestures::TapKind::None;
  if (reason == wake::Reason::Timer) {
    polled_tap = fw::gestures::readTapKind(h.imu);
    if (polled_tap != fw::gestures::TapKind::None) {
      FW_LOG("latched tap picked up on timer wake (kind=%d)", (int)polled_tap);
      reason = wake::Reason::IMU;
    }
  }
  e.reason = static_cast<uint8_t>(reason);

  fw::gestures::TapKind tap = fw::gestures::TapKind::None;
  if (reason == wake::Reason::IMU) {
    tap = polled_tap != fw::gestures::TapKind::None
              ? polled_tap : fw::gestures::readTapKind(h.imu);
    if (tap == fw::gestures::TapKind::None) {
      // Spurious ext0 — skip the whole tick and re-sleep on the same mask.
      FW_LOG("spurious ext0 wake (TAP_SRC empty); re-sleeping%s", "");
      e.mode = static_cast<uint8_t>(wake::persisted().current_mode);
      record_diag();
      h.clock.scheduleWake(
          wake::armMask(wake::persisted().current_mode, local_hour));
      return;
    }
    showTapAck(h.display, tap);
  }

  // Decide path. Non-Timer reasons (ColdBoot, IMU-with-tap, HACommand,
  // SonosFastPath, PostOTA) all want a full refresh. Timer wakes consult the
  // schedule planner; NowPlaying override happens inside planWake().
  wake::Path path;
  if (reason == wake::Reason::Timer) {
    const auto plan = wake::planWake(local_min_of_day, wake::persisted().current_mode);
    path = plan.path;
  } else {
    path = wake::Path::Full;
  }
  e.path = static_cast<uint8_t>(path);
  e.mode = static_cast<uint8_t>(wake::persisted().current_mode);
  FW_LOG("path=%s reason=%s mode=%s min=%d",
         wake::pathName(path), wake::toString(reason),
         fw::modes::toString(wake::persisted().current_mode), local_min_of_day);

  // Skip — schedule says nothing happens this minute. Re-arm and sleep.
  if (path == wake::Path::Skip) {
    record_diag();
    h.clock.scheduleWake(wake::armMask(wake::persisted().current_mode, local_hour));
    return;
  }

  // Partial — offline clock-only refresh. Promote to Full if mode lacks a
  // baked partial zone (Night, NowPlaying, Unknown).
  if (path == wake::Path::Partial) {
    if (doPartial(h, local_now, &e)) {
      record_diag();
      h.clock.scheduleWake(wake::armMask(wake::persisted().current_mode, local_hour));
      return;
    }
    path = wake::Path::Full;
    e.path = static_cast<uint8_t>(path);
  }

  // Network bring-up for Poll, PollPartial, Full.
  const bool wifi = h.transport.wifiConnect();
  FW_LOG("wifi=%d", wifi ? 1 : 0);
  const bool mqtt = wifi ? h.transport.mqttConnect() : false;
  FW_LOG("mqtt=%d", mqtt ? 1 : 0);
  if (wifi) e.flags |= 0x01;
  if (mqtt) e.flags |= 0x02;

  // Poll — read the retained active_mode. If it changed, fall through to
  // Full (so the new face is drawn this wake instead of waiting another
  // minute). If unchanged or MQTT failed, just sleep.
  if (path == wake::Path::Poll) {
    fw::modes::Mode resolved = fw::modes::Mode::Unknown;
    if (mqtt) resolved = resolveActiveMode(h.transport, local_hour);
    if (mqtt && resolved != fw::modes::Mode::Unknown &&
        resolved != wake::persisted().current_mode) {
      FW_LOG("poll detected mode change %s -> %s",
             fw::modes::toString(wake::persisted().current_mode),
             fw::modes::toString(resolved));
      doFull(h, reason, tap, local_hour, local_now, wifi, mqtt, resolved, &e);
      diag_recorded = true;  // doFull's MQTT publish path records the entry
    } else {
      record_diag();
    }
    h.clock.scheduleWake(wake::armMask(wake::persisted().current_mode, local_hour));
    return;
  }

  // PollPartial — same as Poll but on no-change we still do a partial draw.
  // The MQTT fetch piggybacks on the WiFi we already have up; the marginal
  // cost over a pure Partial is one MQTT round-trip.
  //
  // When the active mode has no baked partial zone (Gallery, NowPlaying, etc.)
  // we fall through to Full so the clock zone doesn't get stuck on the
  // 30-minute Full boundary. That keeps the panel visibly fresh for the
  // operator at the cost of one extra Full per cadence boundary in
  // partial-less modes.
  if (path == wake::Path::PollPartial) {
    fw::modes::Mode resolved = fw::modes::Mode::Unknown;
    if (mqtt) resolved = resolveActiveMode(h.transport, local_hour);
    const bool mode_changed =
        mqtt && resolved != fw::modes::Mode::Unknown &&
        resolved != wake::persisted().current_mode;
    if (mode_changed) {
      FW_LOG("poll-partial detected mode change %s -> %s",
             fw::modes::toString(wake::persisted().current_mode),
             fw::modes::toString(resolved));
      doFull(h, reason, tap, local_hour, local_now, wifi, mqtt, resolved, &e);
      diag_recorded = true;
    } else if (!doPartial(h, local_now, &e)) {
      // No zone for this mode — promote to Full so the clock keeps moving.
      doFull(h, reason, tap, local_hour, local_now, wifi, mqtt, std::nullopt, &e);
      diag_recorded = true;
    } else {
      record_diag();
    }
    h.clock.scheduleWake(wake::armMask(wake::persisted().current_mode, local_hour));
    return;
  }

  // Full — the original unrefactored path.
  doFull(h, reason, tap, local_hour, local_now, wifi, mqtt, std::nullopt, &e);
  diag_recorded = true;
  h.clock.scheduleWake(wake::armMask(wake::persisted().current_mode, local_hour));
  if (!diag_recorded) record_diag();
}

}  // namespace fw
