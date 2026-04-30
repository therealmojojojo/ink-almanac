# dashboard-faces Specification

## Purpose
TBD - created by archiving change add-dashboard-faces. Update Purpose after archive.
## Requirements
### Requirement: Shared conventions across all faces

All faces SHALL adhere to shared visual conventions:

- Outer padding of 36u top/bottom and 48u left/right
- Battery percentage indicator in the top-right corner in micro-sized IBM Plex Mono (exception to the 25u size floor). The indicator's value SHALL be sourced from the `device` input — specifically `device.battery.percentage` — on every face. Faces SHALL NOT source the battery value from any other input (it is device state, not climate, Sonos, or pairing state).
- Mode identity is implicit through content and layout; no explicit "SUMMARY" label is drawn anywhere
- Rules are 1u solid or 1u dashed `--faint` (`#a8a8a8`); section dividers are 2u solid `--ink` (`#000`)
- All zones SHALL provide a graceful-degradation treatment when required data is null or unavailable

#### Scenario: Battery indicator placement

- **WHEN** any face is rendered with `device.battery.percentage = 82`
- **THEN** the top-right corner displays a small battery glyph followed by `82%` in IBM Plex Mono

#### Scenario: Battery indicator on every face

- **WHEN** Weather, Gallery, Night, or Now-Playing is rendered with `device.battery.percentage = 82`
- **THEN** each face shows `82%` in the top-right, identical to Summary's treatment — the indicator is not Summary-only

#### Scenario: Device input missing

- **WHEN** `device.json` is absent at render time
- **THEN** every face renders with the battery indicator showing an em-dash label in place of the percentage

#### Scenario: Missing-data fallback

- **WHEN** a zone's required data is null at render time
- **THEN** the zone displays a minimal placeholder (empty rule, short em-dash, or blank) without breaking the layout; the renderer does NOT refuse to render

### Requirement: Zone character budgets

Every dynamic text field is assigned to a named zone with a fixed character budget. This table is the authoritative source; the renderer's `zones.ts` module and any Home Assistant template sensors that pre-truncate upstream SHALL transcribe from it literally. Any change to a budget is a spec change.

**Measurement rules (unchanged from prior version):** lengths in extended grapheme clusters, ellipsis is `…`, HA pre-truncates at word boundary, renderer enforces as last-resort hard cut, verse rejects overflow.

**Budget table (`delight_text` row updated to track `pickFitTier`; remainder unchanged):**

| zone_id         | face         | maxChars | maxLines | kind  | notes                                                |
| --------------- | ------------ | -------- | -------- | ----- | ---------------------------------------------------- |
| weather_cond    | summary      | 18       | 1        | prose |                                                      |
| forecast_cond   | summary      | 14       | 1        | prose |                                                      |
| smart_pill_body | summary      | 50       | 14       | prose | step-down font ladder; cap matches the lowest-rung 19u capacity in `summary.ts:smartPillFontSize` |
| climate_label   | summary      | 12       | 1        | prose |                                                      |
| delight_text    | summary      | 44       | 12       | verse | pill-parity (≥28u) cap from `summary.ts:pickFitTier` tier 4/5 (soft-cpl 44, max-visual-lines 12); tier-7 sub-pill escape extends to 57 / 13 as a relief valve, not a default |
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

Rule-of-thumb checks for `night_phrase` are unchanged.

The `delight_text` row is special: the cell does not enforce a single fixed (cols × lines) budget — `summary.ts:pickFitTier` selects a font tier per item, and each tier has its own (soft-cpl, max-visual-lines) pair. The numbers in this table reflect the **pill-parity floor** (tier 4/5 at 28u): items that fit within `44 / 12` will render at ≥28u in either Phase 1 (unwrapped) or Phase 2 (28u with `.wrap-turnover` hanging indent). Items beyond that floor but within `57 / 13` fall into Phase 3's sub-pill escape (tier 6 at 24u or tier 7 at 22u) — rendered, but smaller than the smart pill that flanks it. The picker (`pairing/corpus_build_triplets_v2.py:pick_fit_tier`) and the validator (`pairing/corpus_validate.py`) SHALL mirror `pickFitTier` rather than re-encoding the budget as a wrap-proxy; the table values exist for upstream truncators (e.g. HA template sensors) that need a single hard cap and cannot run the tier algorithm.

#### Scenario: Night phrase fits budget

- **WHEN** `nightPhrase(0, 15)` returns "quarter past twelve" (19 graphemes)
- **THEN** the value fits within `night_phrase`'s 24-grapheme budget and renders without truncation

#### Scenario: Delight body at pill-parity tier

- **GIVEN** a four-line stanza with longest line 42 chars (e.g. Yeats's *Things fall apart…* opening quatrain)
- **WHEN** `pickFitTier` runs over the body
- **THEN** Phase 1 returns tier 4 (28u, soft-cpl 44, max-visual-lines 11) and the body renders unwrapped, centered, at 28u
- **AND** the picker's `pick_fit_tier(body)` admits the item to the summary-eligible pool

#### Scenario: Delight body needs hanging-indent

- **GIVEN** a four-line stanza with longest line 50 chars (e.g. Donne's *The Sun Rising* opening)
- **WHEN** `pickFitTier` runs over the body
- **THEN** Phase 1 finds no ≥28u tier with `longest ≤ cpl` and falls to Phase 2 — tier 4 with `.wrap-turnover` class applied
- **AND** the renderer left-aligns the section and applies `text-indent: -2em; padding-left: 2em` per `.line` div
- **AND** the picker still admits the item (tier 4 is within pill-parity)

#### Scenario: Delight body needs sub-pill escape

- **GIVEN** a body whose longest line exceeds 44 chars AND whose wrapped visual-line count at 28u exceeds 12
- **WHEN** `pickFitTier` runs over the body
- **THEN** Phases 1 and 2 are skipped and Phase 3 returns tier 6 (24u) or tier 7 (22u)
- **AND** the validator emits a soft warning (renderer can fit, but body falls below the pill-parity floor)
- **AND** the picker admits the item only if the operator has explicitly set `summary_eligible: true`; default-true items at tier 6/7 are flagged for review but not auto-admitted

### Requirement: Summary face layout

Summary SHALL use a three-band composition:

- **Top band (40% height)**: clock on the left (Fraunces opsz 144, size 230u, HH:MM), current-weather block on the right (large temperature, condition, H/L/rain%), separated by a 1u vertical rule
- **Middle band (3-day forecast, ~18% height)**: three equal-width cells separated by dashed rules, each cell showing day-of-week, condition icon, condition label, high/low
- **Bottom band (remaining, with 2u solid rule above)**: two columns separated by a 28u gap. The face content area is 1104u (1200u panel − 2 × 48u face padding), leaving 1076u to allocate. Cell widths SHALL be **577u (delight, left)** and **499u (Smart pill, right)** — the previous 1.45fr / 1fr ratio is replaced by explicit `u` values so the predictor in `debugDelight.ts` and the predictor's audit results stay in lockstep with the rendered face. The split was widened toward the pill by 60u (from a notional 637/439) to give the smart-pill body enough horizontal headroom that 28u Plex Sans accommodates the corpus's authored pill-body lengths without dropping below the readability floor.

The delight zone SHALL follow the pairing's flavor:
- Visual-day flavor → companion is text → delight zone renders short text (haiku, aphorism, fragment) with attribution
- Text-day flavor → companion is visual → delight zone renders a small image with caption

The Smart pill SHALL render a single deep-dive entry (the day's `smart_pill.body` from the triplet's summary slot) at a fixed 28u IBM Plex Sans body with line-height 1.1, text-align justify, hyphens auto. The header label is intentionally absent — the cell reads as primary content beside the delight, not as a chrome-labelled side panel. The earlier dynamic step-down ladder (36u → 21u) is removed; bodies authored above the cell capacity (≈ 455 chars at the post-shift geometry) overflow visibly so the operator catches them at ingestion.

Bilingual haiku/tanka in the delight cell SHALL render in an anthology layout: Japanese original on the left in Noto Serif JP at 30u, translation on the right in Fraunces at 24u, both at a shared 56u line-height so JA[i] and EN[i] sit on a common baseline row. The 24u EN size is one notch below the project-wide 25u readability floor — a documented exception, validated against every bilingual entry in the corpus, made because keeping the parallel layout aligned is the higher priority for this small element.

Monolingual delight bodies SHALL be sized by a content-fit tier rather than by `form`. The renderer (`renderer/src/modes/summary.ts:pickFitTier`) computes the tier from author-line metrics (line count plus the longest line's character count) and emits `data-fit-tier="N"` on the body div; CSS in `summary.css` maps each tier to a (font-size, line-height) pair. The selection algorithm runs three phases:

1. **Phase 1 (preferred)** — find the LARGEST tier ≥28u where every author line fits one visual line at that tier's calibrated cpl AND total line count fits the cell height. This keeps the poet's chosen line breaks intact at the largest possible font.
2. **Phase 2 (wrap-with-turnover)** — if no ≥28u tier admits unwrapped fit, render at 28u with hanging indent on each author line. Tier 4 (28u/34lh) is preferred; tier 5 (28u/30lh) used when tier 4 lacks vertical room. The renderer adds a `.wrap-turnover` class to the section, switching alignment to left and applying `text-indent: -2em; padding-left: 2em` per `.line` div so wrap continuations indent by 2em (Faber/Norton/FSG poetry-typesetting convention).
3. **Phase 3 (sub-pill escape)** — only when neither ≥28u unwrapped nor 28u-with-wrap fits the cell, drop to tier 6 (24u) or tier 7 (22u) for the unwrapped fit. Rare for `summary_eligible: true` items because >5-line work is excluded from the summary pool by convention.

The 28u floor exists for hierarchy: the smart pill on the right is a fixed 28u Plex Sans, and the delight (the day's centerpiece text) MUST NOT read smaller than the pill commentary that flanks it. The Phase 3 escape is a relief valve, not a default.

#### Scenario: Summary with haiku companion

- **WHEN** Summary renders on a visual-day with a haiku companion
- **THEN** the bottom-left delight zone shows the haiku in form-appropriate typography and the haiku's attribution in mono caps

#### Scenario: Summary with small-image companion

- **WHEN** Summary renders on a text-day with an Atget photograph companion
- **THEN** the bottom-left delight zone shows the image with a caption band underneath naming title, artist, and year

### Requirement: Weather face layout

Weather SHALL present two locations with equal treatment, and an astro footer.

- **Header (auto-height)**: mode-headline ("WEATHER"), date inline, time — separated by a 2u solid rule
- **Location rows (1fr, two rows)**: each row has a name + coordinates, a current-conditions block (icon + large temperature + feels-like + H/L/rain), and a 5-day mini-forecast strip. Rows are separated by a 1u dashed rule.
- **Astro footer (auto-height, above a 2u solid rule)**: three equal cells — sunrise/sunset + daylight duration, moon phase (SVG-rendered) + next full-moon date, tonight's astronomical event

Both locations are visually equivalent; neither is privileged.

#### Scenario: Weather with two locations

- **WHEN** Weather renders for "${PLACE_A_NAME}" and "${PLACE_B_NAME}"
- **THEN** both location rows are present, neither is styled as primary, the astro row is visible at the bottom

#### Scenario: No astronomical event tonight

- **WHEN** the astro event feed returns no event for tonight
- **THEN** the astro cell for events shows a short em-dash and a label "no event tonight"

### Requirement: Gallery visual-day layout

Gallery visual-day SHALL present the hero image as a full-frame figure with a minimal caption band.

- **Image area**: occupies the full frame except for a caption band at the bottom (72u tall)
- **Caption band**: title on the left in Fraunces Italic (work title), artist/medium/year in IBM Plex Mono caps letterspaced in the middle, current time on the right in Fraunces (tabular numerals)
- **No other chrome**: no forecast, no labels, no secondary content. The battery indicator remains as the universal exception

The image is pre-dithered by the rendering pipeline; this layout specifies placement only.

#### Scenario: Hiroshige hero

- **WHEN** Gallery visual-day renders with hero `hiroshige-shin-ohashi`
- **THEN** the image fills the frame above a 72u caption band showing the work's title (italic), "UTAGAWA HIROSHIGE · WOODBLOCK · 1857" in mono caps, and the current time

### Requirement: Gallery text-day layout

Gallery text-day SHALL present the hero text as a typeset page with generous margins and per-form typography (dispatched by the rendering pipeline per `typography-routing`).

- **Page margins**: ~120u on each side, ~96u top, ~72u bottom
- **Title** (above the body): Fraunces Italic at display size, centered, when the work has a distinct title; omitted when the first line IS the title (haiku, some aphorisms)
- **Body**: typeset per the form rules from `typography-routing`
- **Attribution** (below the body): IBM Plex Mono caps letterspaced, name + dates (e.g., `MATSUO BASHŌ · 1644–1694`)
- **Caption band**: same as visual-day — title / attribution / time. For text-day, this may be redundant with the attribution line; when redundant, the caption band is suppressed and the time appears in a small corner instead

#### Scenario: Ozymandias renders upright

- **WHEN** Gallery text-day renders Shelley's "Ozymandias" (`form: sonnet`)
- **THEN** the body is typeset in Fraunces Regular (upright) per `typography-routing`, the title "Ozymandias" appears above the body in Fraunces Italic display, and the attribution reads `PERCY BYSSHE SHELLEY · 1792–1822`

#### Scenario: Bashō haiku with no separate title

- **WHEN** Gallery text-day renders a haiku where the first line is the title
- **THEN** no separate title line is rendered above the body; the haiku body appears centered with its attribution below

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

### Requirement: Now-Playing face layout

Now-Playing SHALL present what is currently playing on the kitchen Sonos speaker.

- **Album art (left, ~65% width)**: full-height, pre-dithered by the pipeline
- **Right column (~35% width)**: track title (Fraunces size 64u), artist (IBM Plex Mono caps letterspaced 28u), album (IBM Plex Sans 300, 28u), source indicator (e.g., `SONOS · SPOTIFY` in mono caps 22u at the top)
- **Up-next** (at the bottom-right, small): the next track's title in mono caps 22u, label `NEXT` above it
- **NO progress bar, NO elapsed/total timestamps** — updates occur on track change only

When the Sonos entity is paused, the face MAY continue showing the current track; when idle (no current track), the face is not rendered (the schedule takes over).

#### Scenario: Now-Playing with a Spotify track

- **WHEN** Sonos is playing "Mykonos" by Fleet Foxes from *Sun Giant EP* on Spotify
- **THEN** the face shows the album art dithered on the left, "Mykonos" as Fraunces title, "FLEET FOXES" as mono caps artist, "Sun Giant EP" as Plex Sans album, "SONOS · SPOTIFY" as source tag, and the up-next track in the bottom-right

#### Scenario: Sonos pauses mid-song

- **WHEN** Sonos transitions from `playing` to `paused` during a track
- **THEN** the face is not re-rendered immediately; the current render persists; the schedule resumes only when the Sonos state becomes `idle` for longer than the configured linger (default 90s)

### Requirement: Graceful degradation catalog

Each zone SHALL have an explicit placeholder treatment for missing data. The placeholders are:

- Missing temperature → short em-dash
- Missing condition string → blank
- Missing HN items → list shows `—` per row, up to the row count
- Missing indoor climate → labels render with em-dash values
- Missing forecast day → blank cell (no structure change)
- Missing astro event → "no event tonight" label
- Missing album art → flat `--faint` rectangle with "SONOS" in mono caps overlay
- Missing poetic weather line → render just the hard weather line and the stacked clock; no italic line

#### Scenario: Summary with no HN available

- **WHEN** HN feed is unavailable at render time
- **THEN** Summary still renders with all zones present; the HN list shows two em-dashes in place of titles

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

