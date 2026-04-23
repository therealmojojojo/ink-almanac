## ADDED Requirements

### Requirement: Gallery hero-density for text slots

When a triplet's `gallery` slot resolves to a text item, the text body SHALL contain at least **4 lines**, unless the item's `form` is `haiku` or `tanka`. Body lines are measured by splitting the item's `text` (or first entry of `text_variants` if no `text`) on `\n` and taking the count after trimming surrounding whitespace.

The Gallery face is the day's hero. Its text zones (`poem_body`, `aphorism_body`, `quote_body`) are sized for longer hero content; short texts of 1–3 lines render with the text floating in mostly-empty space and read as sparse rather than emphatic. The Summary face's `delight_text` zone is explicitly sized for short companion texts (4 lines × 24 chars per line), and short texts SHOULD be routed there as `summary` slots.

Haiku and tanka are exempt. The 3-line haiku form is canonical; the Gallery face carries a dedicated `haiku_body` zone sized at exactly 24 × 3 for that form. A 3-line haiku is hero-sized by design.

Short texts (≤ 3 lines, non-haiku/non-tanka) remain fully eligible as `summary` or `anchor`. They are never deleted for this rule — they are routing-constrained, not corpus-excluded.

#### Scenario: Two-line quote in gallery slot

- **WHEN** a triplet declares `gallery: wright-live-forever` where that item has `form: quote` and a 2-line body
- **THEN** validation rejects the triplet with `gallery slot -> 'wright-live-forever' is too short for hero zone (2 lines, form='quote'); short texts (< 4 lines) belong in the summary slot, not gallery (haiku/tanka are exempt)`

#### Scenario: Three-line haiku in gallery slot

- **WHEN** a triplet declares `gallery: basho-old-pond` where that item has `form: haiku` and a 3-line body
- **THEN** validation accepts the triplet; `haiku` and `tanka` are exempt from the line-count floor

#### Scenario: Four-line fragment in gallery slot

- **WHEN** a triplet declares `gallery: sappho-fragment-31` where that item has `form: fragment` and a 4-line body
- **THEN** validation accepts the triplet; 4 lines meets the floor

#### Scenario: Short quote used as summary

- **WHEN** a triplet declares `summary: stein-rose` (2-line `quote`) and `gallery: hokusai-great-wave` (visual)
- **THEN** validation accepts the triplet; the gallery-density rule does not constrain `summary` slots. The `summary` slot is instead governed by `Summary text fits delight_text zone`.
