## 1. Validator

- [x] 1.1 `pairing/corpus_validate.py` rejects a triplet whose `gallery` slot resolves to a text with fewer than 4 body lines, unless the form is `haiku` or `tanka`
- [x] 1.2 Constants `GALLERY_MIN_TEXT_LINES` and `GALLERY_TEXT_SHORT_EXEMPT_FORMS` at module top, with a comment explaining the rationale
- [x] 1.3 Error message names the slot id, observed line count, form, and the floor/exemption

## 2. Pool audit

- [x] 2.1 Audit the 10-triplet active pool — **2** violations found, auto-rejected with `reject-layout` and reason `"auto: gallery text too short for hero zone (N lines, form=Q); short texts belong in summary"`
- [x] 2.2 Count short text items (≤3 lines, non-haiku/tanka) in the corpus — **18**; they remain eligible as `summary` or `anchor`, just not as `gallery`

## 3. Spec

- [x] 3.1 Add "Gallery hero-density for text slots" requirement to `corpus-triplets` spec delta
- [x] 3.2 `openspec validate require-gallery-hero-density` passes

## 4. Out of scope

- Rebuilding the 2 rejected triplets; authoring will re-pair the short texts as summary companions in new triplets.
- A symmetric "summary must be short enough to be companion-shaped" rule — already covered by `require-summary-text-fits-zone` (delight_text ≤ 4 lines × 24 chars).
