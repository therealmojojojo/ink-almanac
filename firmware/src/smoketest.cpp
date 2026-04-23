// Reference-cycling smoke test: pulls polished reference dashboards
// (lmarzen/esp32-weather-epd showcase renders) from the local HTTP server
// and displays them, alternating every N seconds. Purpose: give the operator
// a side-by-side feel for what well-typeset e-paper output looks like on the
// physical panel, so we can iterate typography accordingly.

#if defined(ARDUINO) && defined(SMOKETEST)

#include <Arduino.h>
#include <Inkplate.h>
#include <WiFi.h>

#include "secrets.h"

#ifndef INKPLATE_SMOKETEST_BASE
#define INKPLATE_SMOKETEST_BASE "http://${RENDERER_HOST}:8888"
#endif

#ifndef INKPLATE_SMOKETEST_CYCLE_SECONDS
#define INKPLATE_SMOKETEST_CYCLE_SECONDS 15
#endif

Inkplate display(INKPLATE_3BIT);

static const char* kRefs[] = {
    "/display/weather.png",
    "/display/summary.png",
    "/display/night.png",
    "/display/now-playing.png",
    // Gallery temporarily excluded: its full-greyscale Hopper photo inflates
    // the PNG to ~900 KB, which pngle on the ESP32 can't decode cleanly.
    // Needs server-side palette quantization for photo-heavy modes — planned
    // as a follow-up to this pipeline simplification.
};
#ifndef INKPLATE_SMOKETEST_INVERT
#define INKPLATE_SMOKETEST_INVERT false
#endif
static constexpr size_t kRefCount = sizeof(kRefs) / sizeof(kRefs[0]);

static void showStatus(const char* line) {
  display.clearDisplay();
  display.setTextColor(0);
  display.setTextSize(3);
  display.setCursor(40, 40);
  display.print(line);
  display.display();
}

static bool connectWifi() {
  Serial.println("[smoke] WiFi: connecting...");
  WiFi.mode(WIFI_STA);
  WiFi.begin(INKPLATE_WIFI_SSID, INKPLATE_WIFI_PASSWORD);
  uint32_t t0 = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - t0 < 30000) {
    delay(250);
    Serial.print('.');
  }
  Serial.println();
  if (WiFi.status() != WL_CONNECTED) return false;
  Serial.print("[smoke] IP: ");
  Serial.println(WiFi.localIP());
  return true;
}

static void drawRef(const char* path) {
  char url[192];
  snprintf(url, sizeof(url), "%s%s", INKPLATE_SMOKETEST_BASE, path);
  Serial.print("[smoke] fetch: ");
  Serial.println(url);
  uint32_t t0 = millis();
  display.clearDisplay();
  bool ok = display.drawImage(url, 0, 0, /*invert=*/INKPLATE_SMOKETEST_INVERT, /*dither=*/true);
  if (!ok) {
    Serial.println("[smoke] drawImage FAILED");
    showStatus("drawImage FAILED");
    return;
  }
  display.display();
  Serial.print("[smoke] drew in ");
  Serial.print(millis() - t0);
  Serial.println(" ms");
}

void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.println();
  Serial.println("[smoke] boot — reference mode");
  display.begin();
  showStatus("booting...");
  if (!connectWifi()) {
    showStatus("WiFi FAILED");
    return;
  }
}

void loop() {
  static size_t i = 0;
  if (WiFi.status() != WL_CONNECTED) { delay(5000); return; }
  drawRef(kRefs[i]);
  i = (i + 1) % kRefCount;
  delay(INKPLATE_SMOKETEST_CYCLE_SECONDS * 1000UL);
}

#endif  // ARDUINO && SMOKETEST
