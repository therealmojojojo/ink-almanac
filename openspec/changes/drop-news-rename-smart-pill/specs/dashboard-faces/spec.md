# dashboard-faces — delta

## MODIFIED Requirements

### Requirement: Zone character budgets

Every dynamic text field is assigned to a named zone with a fixed character budget. This table is the authoritative source; the renderer's `zones.ts` module and any Home Assistant template sensors that pre-truncate upstream SHALL transcribe from it literally. Any change to a budget is a spec change.

**Measurement rules (unchanged from prior version):** lengths in extended grapheme clusters, ellipsis is `…`, HA pre-truncates at word boundary, renderer enforces as last-resort hard cut, verse rejects overflow.

**Budget table (`hn_*` rows replaced by `smart_pill_body`; remainder unchanged):**

| zone_id         | face         | maxChars | maxLines | kind  | notes                                                |
| --------------- | ------------ | -------- | -------- | ----- | ---------------------------------------------------- |
| weather_cond    | summary      | 18       | 1        | prose |                                                      |
| forecast_cond   | summary      | 14       | 1        | prose |                                                      |
| smart_pill_body | summary      | 50       | 14       | prose | step-down font ladder; cap matches the lowest-rung 19u capacity in `summary.ts:smartPillFontSize` |
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

The previous `hn_title` and `hn_subtitle` zones are retired together with the Hacker News input (see `ha-integrations` REMOVED requirement and `rendering-pipeline` modified Per-mode input contract).

Rule-of-thumb checks for `night_phrase` are unchanged.

#### Scenario: Smart pill body fits at lowest font rung

- **WHEN** `smart_pill.body` is exactly 372 characters (the 25u capacity in `smartPillFontSize`'s ladder)
- **THEN** the renderer picks 25u and the body fits without truncation

#### Scenario: Smart pill body exceeds floor

- **WHEN** `smart_pill.body` exceeds the budget table's `maxChars`
- **THEN** the picker steps down to the floor and the body may overflow the cell; this is a content-side error to be fixed at curation, not at render

### Requirement: Summary face layout

Summary SHALL use a three-band composition:

- **Top band (40% height)**: clock on the left (Fraunces opsz 144, size 230u, HH:MM), current-weather block on the right (large temperature, condition, H/L/rain%), separated by a 1u vertical rule
- **Middle band (3-day forecast, ~18% height)**: three equal-width cells separated by dashed rules, each cell showing day-of-week, condition icon, condition label, high/low
- **Bottom band (remaining, with 2u solid rule above)**: two columns — left (1.45fr) holds the delight zone (the pairing's companion content: small image OR short text), right (1fr) holds the Smart pill — a single deep-dive entry (word-of-the-day or concept-of-the-day) bound to the day's companion text. The pill body is sourced from the `smart_pill` input (not `news`); the header label is intentionally dropped so the column reads as primary content beside the delight cell, not as a chrome-labelled side panel.

The delight zone SHALL follow the pairing's flavor:
- Visual-day flavor → companion is text → delight zone renders short text (haiku, aphorism, fragment) with attribution
- Text-day flavor → companion is visual → delight zone renders a small image with caption

The Summary face SHALL NOT carry Hacker News, RSS news, or any multi-source news content. The "two-item curated capsule" framing from the original design (word-of-the-day + on-this-day) is retired; the current design is one body per day, sourced from the day's companion sidecar `smart_pill.body` field.

#### Scenario: Summary with haiku companion

(unchanged from existing spec)

#### Scenario: Summary smart-pill body absent

- **WHEN** `smart_pill.json` is present but `body` is empty (or the file is malformed)
- **THEN** the smart-pill cell renders the placeholder em-dash treatment, the rest of Summary renders normally

### Requirement: Night face layout

Night SHALL present a calm, low-content composition suited to ambient night viewing. The clock presentation is **deliberately approximate** — this is a poetic surface, not an information surface; second-level precision is not appropriate and would read as clinical.

- **Top-left (approximate-time phrase)**: Fraunces Italic display size, rendered from the shared `nightPhrase(h, m)` algorithm (see `device-firmware` "Local-tick rendering"). One of: `"{H} o'clock"`, `"quarter past {H}"`, `"half past {H}"`, `"quarter to {H+1}"`, where `{H}` is the English word for the hour (one..twelve). The phrase zone has a stable bounding rectangle declared in `zones.json` and used for both renderer full paints and firmware local-tick partial refreshes.
- **Below phrase**: weekday label in mono caps.
- **Hard weather line**: mono caps small, temp + wind, below the weekday.
- **Nocturne image**: occupies roughly 70% of the remaining frame area, tall-format, pre-dithered by the pipeline.

No indoor climate, no forecast. (The previous "no HN, no news of any kind" allusion is retired since news is no longer a face-level concept anywhere.) No precise HH:MM clock — the precise-clock treatment is reserved for Summary / Weather / Gallery-visual.

#### Scenarios

(unchanged from existing spec)
