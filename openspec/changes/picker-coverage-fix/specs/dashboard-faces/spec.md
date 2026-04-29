# dashboard-faces — delta

## MODIFIED Requirements

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
