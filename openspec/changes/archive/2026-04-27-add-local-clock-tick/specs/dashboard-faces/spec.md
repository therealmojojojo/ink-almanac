## MODIFIED Requirements

### Requirement: Night face layout

Night SHALL present a calm, low-content composition suited to ambient night viewing. The clock presentation is **deliberately approximate** — this is a poetic surface, not an information surface; second-level precision is not appropriate and would read as clinical.

- **Top-left (approximate-time phrase)**: Fraunces Italic display size, rendered from the shared `nightPhrase(h, m)` algorithm (see `device-firmware` "Local-tick rendering"). One of: `"{H} o'clock"`, `"quarter past {H}"`, `"half past {H}"`, `"quarter to {H+1}"`, where `{H}` is the English word for the hour (one..twelve). The phrase zone has a stable bounding rectangle declared in `zones.json` and used for both renderer full paints and firmware local-tick partial refreshes.
- **Below phrase**: weekday label in mono caps.
- **Hard weather line**: mono caps small, temp + wind, below the weekday.
- **Nocturne image**: occupies roughly 70% of the remaining frame area, tall-format, pre-dithered by the pipeline.

No indoor climate, no forecast, no HN, no news of any kind. No precise HH:MM clock — the precise-clock treatment is reserved for Summary / Weather / Gallery-visual.

#### Scenario: Night at 02:14 with clear weather

- **WHEN** Night renders at 02:14 with "Clear, quiet night." as the poetic line
- **THEN** the top-left shows "two o'clock" in Fraunces Italic, the weekday label is present, the (legacy) poetic-weather-line content is rendered below (if the data is still produced), the mono hard-weather line reads something like `-3° · CALM`, and the nocturne image fills the lower-right majority of the frame

#### Scenario: Night at 03:45

- **WHEN** Night renders at 03:45
- **THEN** the top-left shows "quarter to four"

#### Scenario: Firmware local-tick paints the phrase zone

- **WHEN** the firmware performs a `LocalTick` partial refresh at 02:30
- **THEN** only the Night phrase zone (rectangle from `zones.json`) is repainted with "half past two"; the nocturne image and other zones are unchanged

### Requirement: Zone character budgets

Every dynamic text field is assigned to a named zone with a fixed character budget. This table is the authoritative source; the renderer's `zones.ts` module and any Home Assistant template sensors that pre-truncate upstream SHALL transcribe from it literally. Any change to a budget is a spec change.

**Measurement rules (unchanged from prior version):** lengths in extended grapheme clusters, ellipsis is `…`, HA pre-truncates at word boundary, renderer enforces as last-resort hard cut, verse rejects overflow.

**Budget table (Night entries revised to reflect approximate-phrase treatment):**

| zone_id         | face         | maxChars | maxLines | kind  | notes                                                |
| --------------- | ------------ | -------- | -------- | ----- | ---------------------------------------------------- |
| weather_cond    | summary      | 18       | 1        | prose |                                                      |
| forecast_cond   | summary      | 14       | 1        | prose |                                                      |
| hn_title        | summary      | 28       | 2        | prose |                                                      |
| hn_subtitle     | summary      | 32       | 1        | prose |                                                      |
| climate_label   | summary      | 12       | 1        | prose |                                                      |
| delight_text    | summary      | 24       | 4        | verse |                                                      |
| delight_attrib  | summary      | 40       | 1        | prose |                                                      |
| location_name   | weather      | 16       | 1        | prose |                                                      |
| weather_cond_w  | weather      | 18       | 1        | prose |                                                      |
| astro_event     | weather      | 22       | 1        | prose |                                                      |
| astro_detail    | weather      | 26       | 2        | prose |                                                      |
| gallery_title   | gallery      | 20       | 1        | prose |                                                      |
| gallery_attrib  | gallery      | 32       | 1        | prose |                                                      |
| poem_body       | gallery      | 64       | 32       | verse |                                                      |
| haiku_body      | gallery      | 24       | 3        | verse |                                                      |
| aphorism_body   | gallery      | 48       | 6        | verse |                                                      |
| quote_body      | gallery      | 56       | 10       | verse |                                                      |
| weekday_label   | night        | 9        | 1        | prose |                                                      |
| night_phrase    | night        | 24       | 1        | prose | approximate-time phrase from `nightPhrase(h, m)`     |
| poetic_line     | night        | 32       | 1        | prose | (legacy) LLM italic line; kept for continuity        |
| hard_weather    | night        | 16       | 1        | prose |                                                      |
| nocturne_attrib | night        | 40       | 1        | prose |                                                      |
| np_title        | now-playing  | 24       | 2        | prose |                                                      |
| np_artist       | now-playing  | 28       | 1        | prose |                                                      |
| np_album        | now-playing  | 32       | 1        | prose |                                                      |
| np_source       | now-playing  | 20       | 1        | prose |                                                      |
| np_next         | now-playing  | 24       | 1        | prose |                                                      |

Rule-of-thumb checks for `night_phrase`:

- `"quarter past twelve"` is 19 graphemes; well under 24.
- `"quarter to twelve"` is 17 graphemes.
- `"twelve o'clock"` is 14 graphemes.
- The longest phrase the algorithm can produce is `"quarter past twelve"` (19) or `"quarter to twelve"` (17) — both fit.

#### Scenario: Night phrase fits budget

- **WHEN** `nightPhrase(0, 15)` returns "quarter past twelve" (19 graphemes)
- **THEN** the value fits within `night_phrase`'s 24-grapheme budget and renders without truncation

## ADDED Requirements

### Requirement: Clock-zone contract

Each face with a clock SHALL declare a stable clock-zone rectangle (x, y, w, h in panel pixels) that the firmware uses for local-tick partial refreshes. The rectangle is owned by the renderer (it's a layout decision) and exposed to the firmware through the `zones.json` endpoint (see `rendering-pipeline` "Layout metadata").

Declared zones:

- `summary.clock` — the Fraunces HH:MM block at the top-left of the Summary face.
- `weather.clock` — the time in the Weather face header.
- `gallery.clock` — the time in the Gallery caption band (visual or text day).
- `night.phrase` — the Night approximate-time phrase zone (replaces what a precise `night.clock` would otherwise be).
- `now-playing.clock` — explicitly `null`; the Now-Playing face does not do local-tick (the clock is subordinate to album art on this face, and track changes drive refreshes).

The rectangles SHALL be expressed in the same coordinate system used by the panel (1200×825 pixels). Each clock-zone rectangle SHALL be large enough to accommodate the widest value the zone will ever hold (e.g., `23:59` for the digit zones; `quarter past twelve` for the Night phrase zone) without clipping, rendered in the pinned firmware font and size.

When the renderer's layout changes in a way that alters a clock-zone rectangle, the zones.json `version` hash SHALL change, prompting firmware to re-fetch and re-cache on its next cold boot.

#### Scenario: Zones endpoint reports Summary clock rectangle

- **WHEN** a client fetches `GET /display/zones.json`
- **THEN** the response includes `faces.summary.clock = { x: ..., y: ..., w: ..., h: ... }` with numeric values corresponding to the Summary face's clock block in the rendered 1200×825 image

#### Scenario: Night phrase zone accommodates longest phrase

- **WHEN** the Night face layout is rendered at 1200×825 with phrase `"quarter past twelve"` in its declared font and size
- **THEN** the text fits entirely within `faces.night.phrase` as reported by zones.json, with at least 8u of padding on every side

### Requirement: Status-slot rectangle

Each face layout SHALL expose the top-right battery-indicator area as a named `status_slot` rectangle in `zones.json`. The rectangle is the same area the renderer uses to paint the battery indicator (per "Shared conventions across all faces"); this requirement merely names the rectangle so firmware can target its partial-refresh overlays precisely.

The renderer paints the battery indicator into this rectangle on every full render. The firmware MAY partial-refresh a transient status glyph (see `device-firmware` "Status glyphs") over this rectangle, temporarily hiding the battery indicator; the next full refresh repaints the battery indicator and implicitly clears the glyph.

This is a naming-and-coordinate contract, not a new reserved area. The battery indicator convention from "Shared conventions across all faces" remains authoritative; the `status_slot` rectangle simply makes the coordinates machine-readable.

#### Scenario: zones.json reports status slot

- **WHEN** a client fetches `GET /display/zones.json`
- **THEN** each face includes `status_slot: { x, y, w, h }` whose rectangle encloses the battery indicator painted by the renderer in that face's top-right corner, with room for the firmware's ~32×32u status glyph bitmap

#### Scenario: Battery indicator + status glyph share the slot

- **WHEN** a full refresh has just completed and the battery percentage is painted in the `status_slot` rectangle
- **THEN** a subsequent IMU wake may partial-refresh the `ack` glyph into the same rectangle, hiding the battery percentage until the next full refresh repaints it
