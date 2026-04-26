// Firmware main tick — wakes up, resolves mode, fetches PNG, draws, publishes
// device state, arms wake sources. Pure logic over the HAL interfaces so the
// same code runs on-device (with real wrappers) and in the host simulator.

#include "firmware.h"

#include <cmath>
#include <cstring>
#include <ctime>
#include <string>

#include "battery.h"
#include "config.h"
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

int hourOfDay(hal::Epoch now) {
  std::time_t t = static_cast<std::time_t>(now);
  std::tm* gm = std::gmtime(&t);
  return gm ? gm->tm_hour : 0;
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

fw::modes::Mode resolveActiveMode(hal::ITransport& mqtt, int hour) {
  auto payload = mqtt.mqttReadRetained(fw::config::kTopicActiveMode);
  if (!payload.empty()) {
    // Payload might be `summary` or `{"mode":"summary"}`. Accept both.
    std::string as_json = pickString(payload, "mode");
    std::string candidate = trim(as_json.empty() ? payload : as_json);
    auto m = fw::modes::parse(candidate);
    if (m != fw::modes::Mode::Unknown) return m;
  }
  return timeOfDayFallback(hour);
}

std::string rendererUrl(fw::modes::Mode m) {
  // Host sim: the `INKPLATE_RENDERER_BASE` is set via secrets.h on device;
  // on host we allow scenarios to inject the full URL via
  // setRendererResponse(). Both paths end up in this format.
#if defined(INKPLATE_RENDERER_BASE)
  std::string base = INKPLATE_RENDERER_BASE;
#else
  std::string base = "http://renderer.local:8575";
#endif
  return base + "/display/" + fw::modes::toString(m) + ".png";
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
    // No real sleep in the sim — on-device would delay here.
    (void)fw::config::kRendererBackoffSec;
  }
  return false;
}

}  // namespace

void tick(hal::HAL h, wake::Reason reason) {
  const auto now = h.clock.nowEpoch();
  const int hour = hourOfDay(now);

  // Latched-tap polling: without INT1 wired to an ESP32 GPIO the device can't
  // ext1-wake on a tap, but LSM6DSO's LATCHED_INT bit keeps the event visible
  // across deep sleep. On every Timer wake we drain TAP_SRC; if a tap is
  // pending, we upgrade the reason to IMU so the gesture-publish path below
  // runs. Worst-case latency is one timer period (~60 s).
  fw::gestures::TapKind polled_tap = fw::gestures::TapKind::None;
  if (reason == wake::Reason::Timer) {
    polled_tap = fw::gestures::readTapKind(h.imu);
    if (polled_tap != fw::gestures::TapKind::None) {
      FW_LOG("latched tap picked up on timer wake (kind=%d)", (int)polled_tap);
      reason = wake::Reason::IMU;
    }
  }

  fw::gestures::TapKind tap = fw::gestures::TapKind::None;
  if (reason == wake::Reason::IMU) {
    // Reuse the polled kind if we already drained TAP_SRC above; otherwise
    // (ext0 path, or IMU reason from the caller) read it now.
    tap = polled_tap != fw::gestures::TapKind::None
              ? polled_tap
              : fw::gestures::readTapKind(h.imu);

    // Spurious-wake guard. ext0 fired (IO36 went LOW) but TAP_SRC has no
    // single- or double-tap bit set. The pulse came from something other
    // than the IMU: EMI, the SW3 wake button in operator mode, or a
    // sub-threshold motion that briefly toggled INT1. Skip the entire tick —
    // no network bring-up, no fetch, no e-paper refresh — and go straight
    // back to sleep on the same wake sources. See gestures.md "Tap detection".
    if (tap == fw::gestures::TapKind::None) {
      FW_LOG("spurious ext0 wake (TAP_SRC empty); re-sleeping%s", "");
      h.clock.scheduleWake(
          wake::armMask(wake::persisted().current_mode, hour));
      return;
    }
  }

  // Network bring-up. On failure: show placeholder (no PNG), still publish
  // device state if MQTT is up; otherwise arm and sleep.
  const bool wifi = h.transport.wifiConnect();
  FW_LOG("wifi=%d", wifi ? 1 : 0);
  const bool mqtt = wifi ? h.transport.mqttConnect() : false;
  FW_LOG("mqtt=%d", mqtt ? 1 : 0);

  // On an IMU wake the tap is a wake signal, not a policy decision — HA
  // decides what face to show. Publish the gesture first so HA can process
  // it, then open a short grace window on active_mode before committing.
  // If HA responds in-window, we fetch the post-gesture face in this cycle;
  // otherwise we fall back to the pre-gesture retained value and HA's
  // decision lands on the next natural wake.
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
      std::string as_json = pickString(payload, "mode");
      std::string candidate = trim(as_json.empty() ? payload : as_json);
      auto m = fw::modes::parse(candidate);
      if (m != fw::modes::Mode::Unknown) active = m;
    }
  } else if (mqtt) {
    active = resolveActiveMode(h.transport, hour);
  }
  if (active == fw::modes::Mode::Unknown) active = timeOfDayFallback(hour);

  [[maybe_unused]] const bool mode_changed = active != wake::persisted().current_mode;
  FW_LOG("mode=%s changed=%d", fw::modes::toString(active), mode_changed ? 1 : 0);

  // Refresh policy on Inkplate 10 in 3-bit grayscale mode:
  //   ALWAYS FULL.
  //
  // The Soldered Inkplate library's partialUpdate() is a no-op when the
  // panel runs in 3-bit (grayscale) mode — see Inkplate10.cpp:
  //     if (getDisplayMode() == 1) return 0;
  // We need 3-bit for the gallery, nocturne, and companion images (the
  // corpus is built around 8-shade greyscale on this panel), so we live
  // with full refreshes everywhere. Each wake re-fetches the rendered PNG
  // and does a full e-ink update; the clock zone advances at the wake
  // cadence (60 s in summary/weather/gallery, 15 min at night). The brief
  // black flash is visible but acceptable on a wire-tied frame.
  //
  // partial_refresh_count is kept as a counter for symmetry with the spec
  // and the host simulator's MockDisplay assertions, but it never gates a
  // forced full because every refresh on this hardware is already full.

  // Draw the active face. Device path: let the Inkplate library fetch and
  // decode the PNG directly from the URL (pngle streaming). Simulator path:
  // the URL-based call returns false by default, so we fall back to fetching
  // bytes via the transport and handing them to the buffer-based drawImage,
  // which MockDisplay hashes for scenario assertions.
  bool draw_succeeded = false;
  if (wifi) {
    const auto url = rendererUrl(active);
    const bool full = true;  // 3-bit Inkplate 10 — partial is hardware no-op.
    const hal::Rect full_rect{0, 0, 1200, 825};
    FW_LOG("draw full=%d url=%s", full ? 1 : 0, url.c_str());

    const bool drawn_from_url = h.display.drawImageFromUrl(url, full, full_rect);
    if (drawn_from_url) {
      FW_LOG("drew (url path)%s", "");
      if (full) wake::persisted().partial_refresh_count = 0;
      else ++wake::persisted().partial_refresh_count;
      draw_succeeded = true;
    } else {
      hal::HttpResponse resp;
      if (backoffFetch(h.transport, url, &resp)) {
        FW_LOG("resp status=%d len=%u (buffer path)", resp.status, (unsigned)resp.body.size());
        h.display.drawImage(resp.body.data(), resp.body.size(), full, full_rect);
        FW_LOG("drew (buffer path)%s", "");
        if (full) wake::persisted().partial_refresh_count = 0;
        else ++wake::persisted().partial_refresh_count;
        draw_succeeded = true;
      } else {
        FW_LOG("fetch FAILED%s", "");
        // Unavailable indicator — 80×80 corner box (rendered as a no-op on
        // device until a proper glyph exists; MockDisplay records the call).
        uint8_t empty[1] = {0};
        h.display.drawImage(empty, 1, /*full=*/false, hal::Rect{1100, 720, 80, 80});
      }
    }
  }

  // Only advance persisted current_mode when we actually drew the new face.
  // If the draw was skipped (no wifi/mqtt) or failed (fetch error), leave
  // persisted at whatever the panel last successfully showed. The next wake
  // will see mode_changed=true and retry instead of minute-tick-skipping
  // forever with the wrong face stuck on screen.
  //
  // First boot path: persisted is Unknown, draw fails — leave Unknown. The
  // default-to-kSummaryTimerSec branch in timerSecondsFor still gives a
  // sensible 60 s cadence; next wake retries with mode_changed=true.
  if (draw_succeeded) {
    wake::persisted().current_mode = active;
  }

  // Publish device state + any gesture
  if (mqtt) {
    auto reading = fw::battery::read(h.battery);
    auto json = fw::battery::toDeviceStateJson(
        reading, wake::toString(reason), fw::modes::toString(active),
        fw::kBuildVersion);
    h.transport.mqttPublish(fw::config::kTopicDeviceState, json, /*retained=*/true);

    // Gesture publication happens up front (before the grace window) on IMU
    // wakes; republishing here would double-count. Only publish now if the
    // up-front path didn't (e.g., MQTT wasn't yet connected at that point
    // but is now — a corner case not currently exercised).
    if (reason == wake::Reason::IMU && tap != fw::gestures::TapKind::None &&
        !gesture_published) {
      const char* kind = tap == fw::gestures::TapKind::Double ? "double" : "single";
      h.transport.mqttPublish(
          fw::config::kTopicGesture,
          std::string("{\"kind\":\"") + kind + "\"}",
          /*retained=*/false);
    }
  }

  // Arm wake sources for the upcoming sleep.
  h.clock.scheduleWake(wake::armMask(active, hour));
}

}  // namespace fw
