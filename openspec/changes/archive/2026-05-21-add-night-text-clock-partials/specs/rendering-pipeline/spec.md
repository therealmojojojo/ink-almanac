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

The values SHALL be measured live during the Night PNG render via Playwright's `getBoundingClientRect()` on the `.night-phrase` element, populating `clockZoneByMode['night']` (the same map other modes use). The endpoint serves the most-recent measurement; the firmware refreshes its cached rect on every Full wake via `fetchAndStoreClockZone`. (Pre-this-change, `render.ts`'s selector list did not include `.night-phrase` and the Night endpoint returned 404.)

#### Scenario: Firmware fetches Night clock zone after a Night Full

- **WHEN** the device's Full path drew the Night face and ran its post-Full clock-zone fetch (`fetchAndStoreClockZone`)
- **THEN** the renderer responds 200 with `{x, y, w, h, font_size}` for Night; the firmware caches `(x, y)` in `Persisted::clock_zone_*` and uses it for subsequent partial wakes' bitmap blits

### Requirement: bake-night-phrases tool

The renderer repository SHALL ship `renderer/src/tools/bake-night-phrases.ts`, a build-time tool that generates the firmware's baked phrase bitmaps. The tool SHALL:

- Source the 25-phrase list by importing `renderer/src/modes/night.ts::nightPhrase(h, m)` and iterating partial-eligible minutes (`min_of_day % 15 == 0 && min_of_day % 60 != 0` in the Night-tier window 22:00 to 06:30). This keeps the runtime PNG and the baked bitmaps lockstep-consistent. The current `nightPhrase` vocabulary uses "twelve" for the 00:xx hour (matching CSS rendering); switching to "midnight" later requires only updating the function and re-running the bake.
- Inline the Night face's clock font CSS (font-family Fraunces italic, opsz 144, weight 400, font-size 96 px, line-height 1.05) so the baked bitmaps match the rest of the Night face's typography.
- For each phrase: render via Playwright (headless Chromium, deviceScaleFactor 1), threshold to 1-bit (luminance > 240 → white, else black), tight-bounding-box crop.
- Emit `firmware/src/generated/night_phrases.h` (struct decl + `phraseForMinute` decl) and `firmware/src/generated/night_phrases.cpp` (constexpr `uint8_t` arrays for the 25 bitmaps + a switch-statement lookup keyed by minute-of-day).
- Bitmap data SHALL live in `.rodata` (constexpr) so it's flash, not RAM.
- Total flash footprint SHALL be ≤ 200 KB. Empirical bake on 2026-05-20: ~150 KB (max bitmap 684×94 px, ~6 KB/phrase).

The tool SHALL accept a `--smoke` flag that emits a single contact-sheet PNG at `/tmp/night_phrases_preview.png` for the operator to eyeball before committing to a flash. The smoke path SHALL NOT emit the C++ output.

Build-time regeneration via a pre-build hook is a future improvement (deferred from this change). For now the generated files are committed to git alongside the existing `clock_glyphs.{h,cpp}` so contributors do not need Playwright + Chromium installed to compile the firmware; re-baking is done by hand via `npm run bake:night-phrases` whenever the phrase list, the Night CSS, or the bake script itself changes.

#### Scenario: Bake produces a 25-entry table

- **WHEN** `npm run bake-night-phrases` runs after a clean checkout
- **THEN** `firmware/src/generated/night_phrases.cpp` is created with 25 `static constexpr uint8_t kPhrase…[]` arrays, a 25-element `kBitmaps[]` table, and a `phraseForMinute` switch with 25 cases — one for each partial-eligible Night minute (22:15, 22:30, 22:45, 23:15, …, 06:15)

#### Scenario: Smoke flag produces a previewable contact sheet

- **WHEN** the operator runs `npm run bake-night-phrases -- --smoke`
- **THEN** the tool writes `/tmp/night_phrases_preview.png` containing all 25 phrases laid out in a single PNG (e.g., 5×5 grid), so the operator can visually verify font, weight, and rendering before committing
