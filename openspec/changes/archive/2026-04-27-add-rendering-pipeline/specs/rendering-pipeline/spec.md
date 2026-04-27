## ADDED Requirements

### Requirement: HTTP endpoint surface

The renderer SHALL expose the following HTTP endpoints:

- `GET /display/{mode}.png` — returns a 1200×825, 8-bit greyscale PNG with values quantized to the 8-level Inkplate palette `[0, 36, 73, 109, 146, 182, 219, 255]`. `{mode}` is one of `summary`, `weather`, `gallery`, `night`, `now-playing`.
- `GET /display/{mode}/preview` — returns an HTML page rendering the mode at its native 1200×825 size for in-browser development. The page includes a toggle to show the post-processing output (dithered PNG) alongside the raw render for visual comparison.
- `GET /healthz` — returns 200 with a small JSON body when the renderer is alive and Playwright is ready.
- `GET /dither-test` — returns an HTML page walking the six-image dither test results, with inputs and outputs for each test item.

#### Scenario: Fetching summary

- **WHEN** a client sends `GET /display/summary.png`
- **THEN** the response is status 200, `Content-Type: image/png`, body is a valid PNG of exactly 1200×825 with pixel values drawn only from the 8-level Inkplate palette

#### Scenario: Unknown mode

- **WHEN** a client sends `GET /display/foo.png`
- **THEN** the response is status 404 with a small error body naming the unknown mode and listing valid modes

#### Scenario: Healthcheck

- **WHEN** a client sends `GET /healthz`
- **THEN** the response is status 200 within 500ms with JSON body `{ "status": "ok", "playwright_ready": true }`

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

#### Scenario: Network disabled for template loading

- **WHEN** the renderer loads a mode's template
- **THEN** the URL is `file://` or `http://localhost`, never a remote origin (other than cached font CDN at startup)

### Requirement: Image-preparation chain

Between raw Playwright capture and final PNG, output SHALL pass through this chain in order:

1. Convert to single-channel greyscale
2. Remove sRGB gamma (linearize)
3. Apply contrast boost and saturation zero
4. Apply black-point and white-point crush with configurable thresholds (default: black ≤ 0.05 → 0, white ≥ 0.95 → 1.0 before quantization)
5. For image zones only (see dithering requirement), apply palette-aware Floyd-Steinberg
6. Quantize to the 8-level palette
7. Write PNG

Each step SHALL be implemented via `sharp` or equivalent that preserves pixel-exact reproducibility across runs with identical inputs.

#### Scenario: Reproducibility

- **WHEN** the renderer is invoked twice with identical inputs
- **THEN** the two output PNGs are byte-for-byte identical

### Requirement: Selective dithering

Floyd-Steinberg palette-aware dithering SHALL be applied ONLY to pictorial image zones. Specifically:

- **Dithered**: Gallery visual-day hero image, Night mode nocturne image, Now-Playing album art, Summary delight-zone image (when flavor is "text" and the companion is a small visual)
- **Not dithered**: Summary clock/weather/climate/HN, Weather mode entirely, Gallery text-day typeset poem, Night mode clock and weather line, Now-Playing text overlays

Non-dithered zones SHALL be rendered with hard pixel boundaries — no anti-aliasing on text unless explicitly enabled for that zone.

#### Scenario: Summary PNG is sharp

- **WHEN** `/display/summary.png` is rendered and inspected
- **THEN** non-image zones show hard pixel transitions, and the delight-zone image (if present) shows dithering characteristic of Floyd-Steinberg against the Inkplate palette

### Requirement: Inputs contract per mode

Each mode SHALL declare a typed input schema. The renderer SHALL reject any render request whose inputs do not match the schema, returning 400 with a detailed message.

Inputs come from configurable sources:
- A local JSON file or HTTP endpoint for each input category (weather, climate, Sonos, HN, pairing)
- A poll cadence per source (typically on-demand at render time)

Zone character budgets are defined authoritatively by `dashboard-faces` and enforced at the renderer boundary per the Zone budgets requirement below.

#### Scenario: Missing required input

- **WHEN** a render is requested for Summary and the weather input is unavailable
- **THEN** the response is status 503 with a message naming the missing input, and the renderer does NOT fall back to placeholder or stale values for weather (the consumer decides what to do)

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
