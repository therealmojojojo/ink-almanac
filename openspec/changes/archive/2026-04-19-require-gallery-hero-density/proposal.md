## Why

The Gallery face is the day's visual hero — a full page dedicated to one text or image. When a triplet assigns a 1–3 line text to the `gallery` slot (a Hedberg one-liner, a Parker couplet, a single-line Dinescu), the result is mostly whitespace: the hero-density zones (`poem_body` 32 lines, `aphorism_body` 6, `quote_body` 10) are sized for longer content, and the page reads as sparse rather than emphatic.

The Summary face's `delight_text` zone is already sized for exactly this — 4 lines × 24 chars, a small companion panel beside the clock and weather. Short aphoristic texts belong there.

Haiku and tanka are the one exception: a 3-line haiku is canonical and the Gallery has a dedicated `haiku_body` zone sized at exactly 24×3 for that form. Haikus are hero-sized by design.

This change draws the line at **4 body lines**: a text gallery must carry at least 4 lines (or be a haiku/tanka).

## What Changes

- Adds one requirement to `corpus-triplets`: gallery hero-density.
  - A triplet's `gallery` slot, when it resolves to a text item, SHALL have a body of **≥ 4 lines**, unless the item's `form` is `haiku` or `tanka`.
- `pairing/corpus_validate.py` enforces the rule in the gallery-type consistency block of `validate_triplets`.
- Short texts remain eligible as `summary` slots (the summary-text fit rule limits them to the `delight_text` 4-line budget, which matches this rule's floor).

## Capabilities

### Modified Capabilities

- `corpus-triplets`: adds the "Gallery hero-density for text slots" requirement.

## Impact

- **Spec**: one new requirement in `openspec/specs/corpus-triplets/spec.md` after archive.
- **Validator**: new check on `gallery` when the slot is a text (text-day flavor).
- **Existing pool**: 2 active triplets were auto-rejected during this change — `wilde-get-rid-of-t-ma-yuan-scholar-by-twain-truth-rememb` and `twain-schooling-ed-durer-rhinoceros-wright-live-foreve`, both with 2-line Twain / Wright quotes as gallery. Reason recorded on each sidecar.
- **Authoring guidance**: text items with body ≤ 3 lines (18 of the 102 remaining text items — quotes, fragments, 1-line aphorisms) are now explicitly summary-only. They remain in the corpus, eligible as `summary` and `anchor`.
- **No renderer change**: the Gallery face already renders short texts *visually* (no overflow), it just looks sparse. This is an authoring-time taste constraint, enforced at validation.

## Relationship to other changes

Sibling of `require-slot-orientation`, `require-summary-text-fits-zone`, and `require-text-items-fit-zones`. All four rules pin slot assignments to what the face actually does well. This one is a density floor; the others are fit ceilings. Could fold into a combined "slot fits zone" change later.
