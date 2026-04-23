## ADDED Requirements

### Requirement: Summary text fits delight_text zone

When a triplet's `summary` slot resolves to a text item (an item with `text` or `text_variants`), the text body SHALL fit the Summary face's `delight_text` zone budget declared in `renderer/src/zones.ts`: **max 4 lines, max 24 characters per line**.

Enforcement is at validation time. The validator SHALL read the body from `text` or (if absent) the first entry of `text_variants`, split on newlines, and report an error if:

- the number of lines exceeds 4, OR
- any single line has more than 24 characters.

A validation error SHALL include the slot id, the observed line count, the observed maximum line length, and the budget, so the operator can pick a substitute or tighten the fragment without re-reading the item sidecar.

This is a zone-fit requirement, not a taste one. The renderer returns an HTTP `VERSE_OVERFLOW` response for over-budget inputs and refuses to produce a PNG; an over-budget triplet therefore fails to render and violates the pair-stands-alone invariant by producing a blank Summary face.

Image summaries are unaffected (they are subject instead to the orientation and panel-fidelity rules).

The validator's budget constants SHALL mirror `renderer/src/zones.ts` and SHALL be updated when the zone is retuned — drift between the two produces triplets that validate but fail at render, or vice versa.

#### Scenario: Text summary exceeds line count

- **WHEN** a triplet declares `summary: keats-ode-nightingale-fragment` whose `text_variants.en` body spans 34 lines
- **THEN** validation rejects the triplet with `summary slot -> 'keats-ode-nightingale-fragment' text overflows delight_text budget (34 lines, max line N chars; budget 4 lines / 24 chars per line)`

#### Scenario: Text summary exceeds line width

- **WHEN** a triplet declares `summary: gluck-snowdrops` where at least one line of the body is 37 characters long (budget 24)
- **THEN** validation rejects the triplet with the same error message, substituting the observed line count and the 37-char maximum

#### Scenario: Text summary fits

- **WHEN** a triplet declares `summary: basho-old-pond` whose body is three short haiku lines, no line exceeding 24 characters
- **THEN** validation accepts the triplet; the delight_text zone renders without overflow

#### Scenario: Image summary

- **WHEN** a triplet declares `summary: hcb-sunday-marne` (an image item)
- **THEN** this requirement does not apply; image summaries are governed by `Image slot orientation` and `Panel-fidelity constraint on image slots`
