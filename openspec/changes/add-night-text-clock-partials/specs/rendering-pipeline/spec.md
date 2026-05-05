# rendering-pipeline Specification — delta

## ADDED Requirements

### Requirement: Night clock-zone JSON

The renderer SHALL implement `GET /display/night/clock-zone.json` returning a JSON object with the same schema as the other modes' clock-zone endpoints:

```json
{
  "x": <int>,
  "y": <int>,
  "w": <int>,
  "h": <int>,
  "font_size": <int>
}
```

The `(x, y)` is the top-left of the rectangle the firmware will blit phrase bitmaps into. `(w, h)` is the rectangle the post-Full cleanup pulses solid black + white before the over-paint. `font_size` is decorative (the firmware uses the baked phrase bitmaps' inherent dimensions); it's emitted for symmetry with the other modes' endpoints.

The values SHALL be derived from the Night face's CSS layout — either hardcoded constants computed once and pinned, or measured at server startup via a Playwright probe of the rendered Night face. Either source is acceptable; the value SHALL be stable across server restarts and SHALL match the bake-time phrase rectangle (otherwise blits land at the wrong place).

#### Scenario: Firmware fetches Night clock zone after a Night Full

- **WHEN** the device's Full path drew the Night face and ran its post-Full clock-zone fetch (`fetchAndStoreClockZone`)
- **THEN** the renderer responds 200 with `{x, y, w, h, font_size}` for Night; the firmware caches `(x, y)` in `Persisted::clock_zone_*` and uses it for subsequent partial wakes' bitmap blits

### Requirement: bake-night-phrases tool

The renderer repository SHALL ship `renderer/src/tools/bake-night-phrases.ts`, a build-time tool that generates the firmware's baked phrase bitmaps. The tool SHALL:

- Hardcode the 25-phrase list (one per partial-eligible Night minute), in plain lowercase English with "midnight" replacing "twelve" at the 00:xx hour.
- Read the Night face's clock font CSS (font-family, font-size, font-weight, color) at build time so the baked bitmaps match the rest of the Night face's typography.
- For each phrase: render via Playwright (headless Chromium), threshold to 1-bit (luminance > 128 → white, else black), tight-bounding-box crop.
- Emit `firmware/src/generated/night_phrases.h` (struct decl + `phraseForMinute` decl) and `firmware/src/generated/night_phrases.cpp` (constexpr `uint8_t` arrays for the 25 bitmaps + a switch-statement lookup keyed by minute-of-day).
- Bitmap data SHALL live in `.rodata` (constexpr) so it's flash, not RAM.
- Total flash footprint SHALL be ≤ 200 KB (target: ~150 KB at 600×80 px per phrase).

The tool SHALL accept a `--smoke` flag that emits a single contact-sheet PNG at `/tmp/night_phrases_preview.png` for the operator to eyeball before committing to a flash.

The PlatformIO `inkplate10` build environment SHALL invoke the bake tool as a pre-build step when `firmware/src/generated/night_phrases.cpp` is missing or older than (a) the bake script itself, (b) the Night face's CSS, or (c) the phrase list inside the bake script. The CMake host build SHALL mirror via `add_custom_command` so simulator tests compile against the same generated file.

#### Scenario: Bake produces a 25-entry table

- **WHEN** `npm run bake-night-phrases` runs after a clean checkout
- **THEN** `firmware/src/generated/night_phrases.cpp` is created with 25 `static constexpr uint8_t kPhrase…[]` arrays, a 25-element `kBitmaps[]` table, and a `phraseForMinute` switch with 25 cases — one for each partial-eligible Night minute (22:15, 22:30, 22:45, 23:15, …, 06:15)

#### Scenario: Smoke flag produces a previewable contact sheet

- **WHEN** the operator runs `npm run bake-night-phrases -- --smoke`
- **THEN** the tool writes `/tmp/night_phrases_preview.png` containing all 25 phrases laid out in a single PNG (e.g., 5×5 grid), so the operator can visually verify font, weight, and rendering before committing
