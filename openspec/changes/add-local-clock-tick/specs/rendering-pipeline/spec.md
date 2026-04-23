## MODIFIED Requirements

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

## ADDED Requirements

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
