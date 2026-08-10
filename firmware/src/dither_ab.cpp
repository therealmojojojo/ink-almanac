// Dither A/B probe — hardware validation for `move-dither-server-side`.
//
// Alternates the SAME rendered face two ways so the operator can photograph
// both under identical lighting:
//
//   A: full-range greyscale PNG, drawn with dither=true
//      -> exactly what the panel does today
//   B: palette-constrained PNG, drawn with dither=false
//      -> the proposed path
//
// The question this answers is whether the Inkplate library's monochrome
// Floyd-Steinberg really does render ~19/255 bright with 7.5x the error of a
// correct pass, as simulation predicts. That evidence is a port of
// ImageDither.cpp, not a photograph, so it gates the rollout — see
// openspec/changes/move-dither-server-side/tasks.md group 5.
//
// Deliberately separate from smoketest.cpp: this installs no production
// firmware, so a bad result costs one reflash of `inkplate10` and nothing else.
//
// Serve the two PNGs with:
//   cd <scratch>/hw/ab && python3 -m http.server 8888 --bind 0.0.0.0
// Flash with:
//   pio run -e dither_ab -t upload && pio device monitor -e dither_ab

#if defined(ARDUINO) && defined(DITHER_AB)

#include <Arduino.h>
#include <Inkplate.h>
#include <WiFi.h>

#include "secrets.h"

#ifndef DITHER_AB_BASE
#define DITHER_AB_BASE "http://192.168.1.131:8888"
#endif

#ifndef DITHER_AB_CYCLE_SECONDS
#define DITHER_AB_CYCLE_SECONDS 15
#endif

Inkplate display(INKPLATE_3BIT);

struct Ref {
  const char* path;
  bool dither;      // passed straight to Inkplate::drawImage
  const char* tag;  // drawn top-left so photographs are self-identifying
  const char* note;
};

#ifdef DITHER_AB_WEDGE
// Panel-calibration mode: draw the step wedge once and hold it, so the panel
// is not mid-refresh while being photographed. dither=false is mandatory —
// with dithering on, the measurement would be of the dither, not the levels.
static const Ref kRefs[] = {
    {"/wedge.png", false, "W", "step wedge (calibration)"},
};
#else
static const Ref kRefs[] = {
    {"/1EF-side.png", false, "", "Goya  E Floyd-Steinberg | F blue noise"},
    {"/2EF-side.png", false, "", "Hiroshige  E Floyd-Steinberg | F blue noise"},
    {"/3EF-side.png", false, "", "Redon  E Floyd-Steinberg | F blue noise"},
    {"/4EF-side.png", false, "", "Rembrandt  E Floyd-Steinberg | F blue noise"},
    {"/1BE-side.png", false, "", "Goya  B chromium | E lanczos resample"},
    {"/2BE-side.png", false, "", "Hiroshige  B chromium | E lanczos resample"},
    {"/3BE-side.png", false, "", "Redon  B chromium | E lanczos resample"},
    {"/4BE-side.png", false, "", "Rembrandt  B chromium | E lanczos resample"},
};
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
  Serial.println("[ab] WiFi: connecting...");
  WiFi.mode(WIFI_STA);
  WiFi.begin(INKPLATE_WIFI_SSID, INKPLATE_WIFI_PASSWORD);
  uint32_t t0 = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - t0 < 30000) {
    delay(250);
    Serial.print('.');
  }
  Serial.println();
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[ab] WiFi: FAILED");
    return false;
  }
  Serial.print("[ab] IP: ");
  Serial.println(WiFi.localIP());
  return true;
}

#ifdef DITHER_AB_WEDGE
// Flush residual charge before a measurement draw.
//
// The first calibration photograph showed the previous image faintly under the
// patches, which biases a reflectance reading — the whole point of the target
// is that a patch shows ONLY its own level. clearDisplay() alone just zeroes
// the framebuffer; shifting the particles needs actual full black/white
// refreshes. In 3-bit mode fillScreen takes a level, 0 = black, 7 = white.
static void ghostClear(int cycles) {
  for (int i = 0; i < cycles; ++i) {
    Serial.printf("[ab] ghost-clear %d/%d\n", i + 1, cycles);
    display.fillScreen(0);
    display.display();
    delay(400);
    display.fillScreen(7);
    display.display();
    delay(400);
  }
  // Let the display settle before the measured draw.
  delay(1500);
}
#endif

static void drawRef(const Ref& ref) {
  char url[192];
  snprintf(url, sizeof(url), "%s%s", DITHER_AB_BASE, ref.path);
  Serial.printf("[ab] %s  dither=%d  %s\n", ref.tag, ref.dither ? 1 : 0, url);

  uint32_t t0 = millis();
  display.clearDisplay();
  // Signature is drawImage(path, x, y, dither, invert).
  const bool ok = display.drawImage(url, 0, 0, ref.dither, /*invert=*/false);
  if (!ok) {
    // A failure here is itself a result: it is how the oversized full-range
    // Gallery PNG behaves, which is why smoketest.cpp excludes that face.
    Serial.printf("[ab] %s DRAW FAILED (decode or fetch)\n", ref.tag);
    showStatus(ref.dither ? "A FAILED" : "B FAILED");
    return;
  }

  // Tag in the top-left corner, on bare paper for every current gallery
  // layout, so the two photographs can be told apart afterwards.
  if (ref.tag[0] != '\0') {
    display.setTextColor(0);
    display.setTextSize(4);
    display.setCursor(10, 8);
    display.print(ref.tag);
  }

  display.display();
  Serial.printf("[ab] %s drew in %lu ms  (%s)\n", ref.tag,
                (unsigned long)(millis() - t0), ref.note);
}

void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.println();
  Serial.println("[ab] boot — dither A/B probe");
  Serial.println("[ab] A = device dither (today), B = server dither (proposed)");
  display.begin();
  showStatus("dither A/B: booting");
  if (!connectWifi()) {
    showStatus("WiFi FAILED");
    return;
  }
}

void loop() {
  static size_t i = 0;
  if (WiFi.status() != WL_CONNECTED) {
    delay(5000);
    return;
  }
#ifdef DITHER_AB_WEDGE
  // Flush the previous image out of the particles before the measured draw.
  ghostClear(3);
#endif
  drawRef(kRefs[i]);
  i = (i + 1) % kRefCount;
#ifdef DITHER_AB_WEDGE
  // Draw once, then idle. A repainting panel cannot be photographed cleanly,
  // and e-ink holds the image without power anyway.
  Serial.println("[ab] wedge held — panel is static, safe to photograph");
  while (true) delay(10000);
#else
  delay(DITHER_AB_CYCLE_SECONDS * 1000UL);
#endif
}

#endif  // ARDUINO && DITHER_AB
