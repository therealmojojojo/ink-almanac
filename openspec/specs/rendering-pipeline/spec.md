# rendering-pipeline Specification

## Purpose
TBD - created by archiving change add-rendering-pipeline. Update Purpose after archive.
## Requirements
### Requirement: HTTP endpoint surface

The renderer SHALL expose the following HTTP endpoints:

- `GET /display/{mode}.png` — returns a 1200×825, 8-bit greyscale PNG with values quantized to the 8-level Inkplate palette `[0, 36, 73, 109, 146, 182, 219, 255]`. `{mode}` is one of `summary`, `weather`, `gallery`, `night`, `now-playing`.
- `GET /display/{mode}/preview` — returns an HTML page rendering the mode at its native 1200×825 size for in-browser development.
- `GET /display/zones.json` — returns layout metadata (clock-zone and status-glyph-slot rectangles per face) used by the device firmware for local-tick rendering. See "Layout metadata" below.
- `GET /healthz` — returns 200 with a small JSON body when the renderer is alive and Playwright is ready.
- `GET /dither-test` — returns an HTML page walking the dither test results.

#### Scenario: Fetching summary

- **WHEN** a client sends `GET /display/summary.png`
- **THEN** the response is status 200, `Content-Type: image/png`, body is a valid PNG of exactly 1200×825 with pixel values drawn only from the 8-level Inkplate palette

#### Scenario: Fetching zones metadata

- **WHEN** a client sends `GET /display/zones.json`
- **THEN** the response is status 200, `Content-Type: application/json`, body conforms to the schema in "Layout metadata"

#### Scenario: Unknown mode

- **WHEN** a client sends `GET /display/foo.png`
- **THEN** the response is status 404 with a small error body naming the unknown mode and listing valid modes

#### Scenario: Healthcheck

- **WHEN** `GET /healthz` is issued
- **THEN** the renderer returns 200 with a small JSON body including `{ ok: true }` and a build/version string

### Requirement: Output specifications

Every rendered PNG SHALL conform to the following:

- Exact dimensions 1200×825 pixels
- 8-bit greyscale (single channel)
- Pixel values restricted to the palette `[0, 36, 73, 109, 146, 182, 219, 255]`
- No alpha channel
- sRGB colorspace, or none

#### Scenario: Out-of-palette value

- **WHEN** a rendered PNG is inspected and contains any pixel with a value not in the Inkplate palette
- **THEN** the rendering pipeline's self-test reports a failure for that mode

### Requirement: Rendering engine

Rendering SHALL use Playwright with Chromium at a fixed viewport of 1200×825, `deviceScaleFactor: 1`. Template URLs SHALL be resolved locally (no external network for the HTML itself); external font loading via `@font-face` is permitted and SHALL be cached at startup.

The Chromium screenshot SHALL be converted to a single-channel 8-bit greyscale PNG via `sharp.greyscale()` and returned as the response body for `/display/{mode}.png`. No server-side supersample, Lanczos resample, contrast manipulation, or palette quantization is performed in the default path.

#### Scenario: Network disabled for template loading

- **WHEN** the renderer loads a mode's template
- **THEN** the URL is `file://` or `http://localhost`, never a remote origin (other than cached font CDN at startup)

#### Scenario: Raw PNG dimensions

- **WHEN** a mode is rendered via `/display/{mode}.png`
- **THEN** the returned PNG is exactly 1200×825, 8-bit greyscale, and was produced from a single Chromium screenshot — not via an intermediate upscale/downsample pass

### Requirement: Image-preparation chain

Between Chromium screenshot and returned PNG, the renderer SHALL perform exactly one transformation: greyscale conversion via `sharp.greyscale()`. Output SHALL be an 8-bit greyscale PNG.

The renderer SHALL NOT apply linearization, contrast adjustment, endpoint crush, Floyd-Steinberg error diffusion, or palette quantization in the default path. The device's Inkplate library performs its own Floyd-Steinberg dither onto the 8-shade panel palette during `drawImage()` decode; any server-side palette manipulation compounds with the library's dither and produces visible smudge on the physical panel.

#### Scenario: Reproducibility

- **WHEN** the renderer is invoked twice with identical inputs
- **THEN** the two output PNGs are byte-for-byte identical

#### Scenario: Greyscale output, not palette-quantized

- **WHEN** a mode PNG is inspected pixel-by-pixel
- **THEN** pixel values span the full 0–255 greyscale range (the library will quantize them on device), and are NOT constrained to the 8-shade Inkplate palette at this stage

### Requirement: Selective dithering

Server-side Floyd-Steinberg dithering SHALL NOT be applied in the default path. The device's Inkplate library performs Floyd-Steinberg error diffusion onto the 8-shade panel palette during image decode when `drawImage(url, x, y, invert=false, dither=true)` is called; this is the single dither pass the pipeline relies on.

A future change MAY reintroduce server-side palette mapping for specific modes that embed large photos (Gallery, Night) whose unquantized greyscale PNGs overflow the device's pngle decoder memory budget. That change will scope the server-side step to photo zones only, will set `dither=false` in firmware for those modes so the server output is not re-dithered, and will document the added processing as an explicit exception to this default.

#### Scenario: No double-dithering

- **WHEN** a mode PNG is returned by the renderer and drawn by the device with `dither=true`
- **THEN** the device has performed exactly one Floyd-Steinberg pass on the pixel data — the renderer contributed zero dither passes — and glyph edges on the panel are visually crisp (no palette-noise halo around hard edges)

### Requirement: Inputs contract per mode

Each mode SHALL declare a typed input schema. The renderer SHALL reject any render request whose inputs do not match the schema, returning 400 with a detailed message.

Inputs come from configurable sources:
- A local JSON file at `RENDERER_INPUTS_DIR/<name>.json` — the canonical surface the renderer reads.
- `POST /inputs/:name` (see Input-publisher endpoint) — the canonical surface HA writes.

Per-mode required inputs:
- `summary` ← `clock, weather, climate, smart_pill, pairing, device`
- `weather` ← `clock, weather, device`
- `gallery` ← `clock, pairing, device`
- `night` ← `clock, weather, pairing, device`
- `now-playing` ← `clock, sonos, device`

`device` is listed as a required input across all faces because the shared battery indicator applies to all of them. When `device.json` is absent, the renderer SHALL NOT return 503 solely on that basis — the indicator falls back to its graceful-degradation treatment per `dashboard-faces`. Every other required input, if absent, returns 503 naming the missing file.

The `smart_pill` input SHALL carry the body text for Summary's smart-pill section (a deep-dive entry — word-of-the-day or concept-of-the-day — bound to the day's companion text). The previous name `news` is retired; it was residue from an earlier multi-source RSS design that no longer exists. Likewise the previous `hn` input (Hacker News top-N) is retired; the device does not surface news of any kind.

Zone character budgets are defined authoritatively by `dashboard-faces` and enforced at the renderer boundary per the Zone budgets requirement below.

#### Scenario: Missing required smart_pill input

- **WHEN** a client requests `GET /display/summary.png` and `RENDERER_INPUTS_DIR/smart_pill.json` is absent
- **THEN** the renderer returns 503 with a body naming the missing file (`smart_pill.json`); the response is not cached

#### Scenario: Legacy `news` input present is ignored

- **WHEN** an old `RENDERER_INPUTS_DIR/news.json` exists alongside `smart_pill.json`
- **THEN** the renderer reads `smart_pill.json` and ignores `news.json`; `news` is not a valid input name

### Requirement: Zone budget enforcement

The renderer SHALL enforce the per-zone character budgets defined in `dashboard-faces` as a final safety net against layout overflow. Enforcement rules:

- **Prose zones** (e.g., track title, HN title, astro event detail, poetic weather line, weather condition): when input length exceeds the budget, the renderer hard-cuts to `maxChars × maxLines − 1` graphemes and appends `…` (U+2026). The renderer does NOT attempt word-boundary truncation; producers (HA template sensors) are expected to pre-truncate at word boundaries upstream, and the renderer's cut is a last-resort safety net.
- **Verse zones** (any zone marked `kind: verse` in the budget table, e.g., haiku body, poem body, aphorism body): when input length exceeds the budget, the renderer SHALL reject the render with status 422 and a message naming the offending zone and input length. Verse is never truncated. Upstream (the pairing pipeline) is responsible for ensuring verse items fit their target zones.
- **Length is measured in extended grapheme clusters** (Unicode UAX #29), not UTF-16 code units, so Romanian precomposed diacritics (`ă`, `â`, `î`, `ș`, `ț`) count as one character each. The budget table is authoritative on visual-width assumptions; if a specific zone needs a narrower budget due to wide glyphs at its set size, that tuning lives in the budget table, not in the renderer.

The renderer SHALL source budgets from a single `zones.ts` module whose values transcribe the table in `dashboard-faces/spec.md`. A build-time check SHALL fail if `zones.ts` and the spec table diverge.

#### Scenario: Prose overflow is truncated with ellipsis

- **WHEN** Summary is rendered with a track title of 60 graphemes and the `track_title` zone budget is `maxChars: 28, maxLines: 2, kind: prose`
- **THEN** the renderer hard-cuts the input to 55 graphemes and appends `…`, rendering `… "` as the final character

#### Scenario: Verse overflow is rejected

- **WHEN** Gallery text-day is rendered with a haiku body of 4 lines and the `haiku_body` zone budget is `maxChars: 24, maxLines: 3, kind: verse`
- **THEN** the response is status 422 with a message naming `haiku_body` and the offending input length; no PNG is produced

#### Scenario: Romanian diacritics count as one grapheme

- **WHEN** an input contains `"Să nu uităm"` (11 graphemes) and the zone budget is `maxChars: 11, maxLines: 1, kind: prose`
- **THEN** the input fits exactly and is rendered without truncation

#### Scenario: Budget drift detected

- **WHEN** the renderer builds and `zones.ts` declares a budget that does not match the `dashboard-faces/spec.md` table
- **THEN** the build fails with a message naming the divergent zone

### Requirement: Visual snapshot testing

The renderer SHALL include a snapshot test suite that renders every mode against a fixture set of inputs and diffs the output against a golden PNG stored in the repository. Any diff exceeding a configurable threshold (default: 5 pixels) SHALL fail the test.

Fixtures SHALL cover at minimum:
- Summary with a bilingual haiku delight, partly cloudy weather, mid-range climate, 2 HN items
- Weather with both locations, astro event present, moon at waxing gibbous
- Gallery visual-day with a representative dithered image
- Gallery text-day with each form variant (haiku, sonnet, free-verse, fragment, aphorism, quote)
- Night with mid-month moon, cold clear weather
- Now-Playing with a Spotify source, medium-length title, medium-length artist

#### Scenario: Template change breaks a mode

- **WHEN** a change to `shared/tokens.css` causes Summary to render differently
- **THEN** the snapshot test for Summary fails with a diff image highlighting changed pixels, and the suite exits non-zero

### Requirement: Dither test harness

A `GET /dither-test` endpoint SHALL present per-category test renders of 6 standard test images (one from each strong category: etching, woodblock, photograph-FSA, chiaroscuro; and two weak categories: color-painting, color-photography) to validate that the dither pipeline produces the expected results on representative content. The output SHALL also be written to `docs/dither-test-results.md` whenever the test harness is run.

#### Scenario: Running the dither test

- **WHEN** the operator runs the dither test harness
- **THEN** `docs/dither-test-results.md` is regenerated with current-date output, including the original and dithered version of each test image and a brief per-item note on fidelity

### Requirement: Local operation

The renderer SHALL run on the Mac host, not inside the HAOS VM. It SHALL listen on a configurable port (default 8575) on the host's LAN interface, reachable from both the HAOS VM and, eventually, the Inkplate device.

The renderer SHALL start automatically at host boot via a launchd user agent.

#### Scenario: Reachable from HAOS

- **WHEN** HAOS sends `GET http://{host-ip}:8575/healthz` on the LAN
- **THEN** the response is 200 within 500 ms

#### Scenario: Auto-start at boot

- **WHEN** the Mac host reboots
- **THEN** within 60 seconds of boot, `/healthz` returns 200 without manual intervention

### Requirement: Input-publisher endpoint

The renderer SHALL expose `POST /inputs/:name` that writes a JSON body atomically to `RENDERER_INPUTS_DIR/${name}.json`.

- `:name` MUST match `^[a-z0-9_-]+$` and MUST be one of the allowed input names (`clock`, `weather`, `climate`, `smart_pill`, `pairing`, `sonos`, `device`). Other values return 404.
- Requests MUST carry `Authorization: Bearer <token>` matching the renderer's `RENDERER_INPUT_TOKEN` environment variable. Missing header returns 401; mismatched token returns 403.
- Request body MUST be `application/json` and ≤ 256 KB. Larger bodies return 413.
- On success the renderer writes to a temp file in the inputs directory, then `rename`s it over the destination path, returning 204 No Content.
- The endpoint SHALL NOT validate the JSON body against a mode schema — schema validation happens at read time on the next `/display/*.png` request. This preserves the existing "inputs are loose, render enforces" contract.

The legacy input names `news` and `hn` are no longer accepted; requests with those `:name` values return 404.

#### Scenario: Authenticated write to smart_pill lands

- **WHEN** the pairing publisher PUTs a valid JSON body to `/inputs/smart_pill` with a matching bearer token
- **THEN** the renderer writes the file atomically and returns 204; a subsequent `GET /display/summary.png` reflects the new body

#### Scenario: Legacy `news` POST rejected

- **WHEN** any client POSTs to `/inputs/news`
- **THEN** the renderer returns 404 because `news` is no longer in the input-name allowlist

### Requirement: Device input schema

Every mode SHALL accept a `device` input with the following schema:

```
device: {
  battery: {
    percentage: number (0..100, integer preferred)
    voltage?:   number
  }
  build?:     string
  last_seen?: string (ISO-8601)
}
```

The input is **optional at the schema level**: when `device.json` is absent, the renderer SHALL render the face with the battery indicator in its graceful-degradation treatment (em-dash label per `dashboard-faces`). A present-but-malformed `device.json` SHALL return 400 from `/display/*.png` per the existing Zod validation path.

The renderer SHALL pass `input.device?.battery?.percentage` to the shared `batteryIndicator` helper in every face module (`summary.ts`, `weather.ts`, `gallery.ts`, `night.ts`, `nowPlaying.ts`).

#### Scenario: All faces show the battery

- **WHEN** `device.json` contains `{battery: {percentage: 82}}` and any face is rendered
- **THEN** the top-right battery indicator shows `82%`, not an em-dash

#### Scenario: Missing device input degrades gracefully

- **WHEN** `device.json` is absent at render time
- **THEN** the renderer does NOT return 503; it renders the face with the em-dash battery treatment and logs a single info-level line naming the missing input

### Requirement: Layout metadata

The renderer SHALL expose `GET /display/zones.json` returning a JSON document with the following shape:

```json
{
  "version": "sha256:<64-hex>",
  "faces": {
    "summary":     { "clock": { "x": 0, "y": 0, "w": 0, "h": 0 }, "status_slot": { "x": 0, "y": 0, "w": 0, "h": 0 } },
    "weather":     { "clock": { "x": 0, "y": 0, "w": 0, "h": 0 }, "status_slot": { "x": 0, "y": 0, "w": 0, "h": 0 } },
    "gallery":     { "clock": { "x": 0, "y": 0, "w": 0, "h": 0 }, "status_slot": { "x": 0, "y": 0, "w": 0, "h": 0 } },
    "night":       { "phrase": { "x": 0, "y": 0, "w": 0, "h": 0 }, "status_slot": { "x": 0, "y": 0, "w": 0, "h": 0 } },
    "now-playing": { "clock": null, "status_slot": { "x": 0, "y": 0, "w": 0, "h": 0 } }
  }
}
```

- `version` is the sha256 hash of the canonical layout source (e.g., `renderer/src/zones.ts` plus relevant CSS tokens). It changes when any rectangle changes.
- Each rectangle is in panel pixel coordinates (1200×825 origin top-left).
- Faces without a local-tick clock zone return `"clock": null` (Now-Playing today).
- The Night face uses `"phrase"` instead of `"clock"` to make it explicit that the zone holds a phrase, not a HH:MM string.
- `status_slot` is the top-right rectangle the renderer already paints the battery indicator into (per `dashboard-faces` shared conventions); firmware uses these coordinates to overlay transient status glyphs on top of the battery indicator, which is restored on the next full refresh.

The endpoint is unauthenticated — the response contains only public layout metadata, no content, no secrets.

#### Scenario: Version changes when layout changes

- **WHEN** a developer changes the clock placement on the Summary face in the renderer source and redeploys
- **THEN** `GET /display/zones.json` returns a different `version` hash than before; firmware consuming zones.json re-caches on its next cold boot

#### Scenario: Schema validation on startup

- **WHEN** the renderer starts up and assembles the zones table
- **THEN** each declared rectangle is validated: `x ≥ 0`, `y ≥ 0`, `x + w ≤ 1200`, `y + h ≤ 825`; startup fails loudly if any rectangle is out of bounds

### Requirement: Night face approximate-time phrase

The Night face SHALL render an approximate-time phrase in place of a precise HH:MM clock, computed from the incoming clock time using the `nightPhrase(h, m)` algorithm shared with the firmware.

Algorithm (MUST be identical to the firmware's implementation — divergence is a spec violation):

```
nightPhrase(h, m):
  hour12     = ((h + 11) mod 12) + 1
  nextHour12 = (hour12 mod 12) + 1
  if  0 <= m <= 14: return "{word(hour12)} o'clock"
  if 15 <= m <= 29: return "quarter past {word(hour12)}"
  if 30 <= m <= 44: return "half past {word(hour12)}"
  if 45 <= m <= 59: return "quarter to {word(nextHour12)}"

word(h12):   // 1..12 -> "one" ... "twelve"
```

The renderer SHALL compute the phrase from its `clock` input at render time (not accept it as a pre-computed string), so the single source of truth is the algorithm. Both the renderer (for full fetches) and the firmware (for 15-min local ticks) SHALL run the same algorithm; agreement is structural.

The phrase fits the `night_phrase` zone budget defined in `dashboard-faces` (≤ 24 graphemes, 1 line).

#### Scenario: Phrase at 02:14

- **WHEN** the Night face renders with `clock.time = "02:14"`
- **THEN** the phrase zone reads "two o'clock"

#### Scenario: Phrase at boundary 02:15

- **WHEN** the Night face renders with `clock.time = "02:15"`
- **THEN** the phrase zone reads "quarter past two"

#### Scenario: Phrase at 23:50

- **WHEN** the Night face renders with `clock.time = "23:50"`
- **THEN** the phrase zone reads "quarter to twelve"

#### Scenario: Phrase at 00:07

- **WHEN** the Night face renders with `clock.time = "00:07"`
- **THEN** the phrase zone reads "twelve o'clock"

### Requirement: Status-slot coordinates in zones.json

The `status_slot` rectangle exposed in `zones.json` SHALL correspond to the top-right battery-indicator area specified in `dashboard-faces` "Shared conventions across all faces". The renderer already paints the battery indicator into this area on every full render; the rectangle is declared in zones.json so firmware can overlay transient status glyphs (see `device-firmware` "Status glyphs") with pixel-exact coordinates.

The rectangle SHALL be large enough to contain the firmware's ~32×32u status-glyph bitmap without clipping, plus the battery indicator's rendered bounding box, whichever is larger. In practice this means a small amount of padding around the battery-indicator area so either paint target fits.

No new layout reservation is created by this requirement — the battery indicator has always lived there; zones.json simply names it.

#### Scenario: Status slot reported for Gallery visual-day

- **WHEN** a client fetches `GET /display/zones.json`
- **THEN** `faces.gallery.status_slot` is a rectangle in the top-right of the 1200×825 frame that encloses both the rendered battery percentage and a ~32×32u glyph overlay with adequate padding

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

