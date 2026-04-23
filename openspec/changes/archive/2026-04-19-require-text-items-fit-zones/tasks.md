## 1. Validator

- [x] 1.1 `pairing/corpus_validate.py`'s `validate_text` enforces body fit against `GALLERY_TEXT_BUDGET[form]` (maxChars × maxLines)
- [x] 1.2 Items with `form` outside the gallery-text taxonomy are rejected (`haiku|tanka|sonnet|free-verse|stanzaic|fragment|prose-poem|aphorism|quote`)
- [x] 1.3 `poem_body` forms additionally enforce a practical 16-line vertical cap (`POEM_BODY_SOFT_LINE_CAP`) because the 2-column flow caps at 8 lines/col
- [x] 1.4 Budget constants (`GALLERY_TEXT_BUDGET`, `POEM_BODY_FORMS`, `POEM_BODY_SOFT_LINE_CAP`) live at module top with a comment pointing at `renderer/src/zones.ts` + `renderer/src/modes/gallery.ts`
- [x] 1.5 Rejected triplets are skipped by `validate_triplets` integrity checks (refs, forms, orientation, fidelity, zone fit)

## 2. Pool cleanup (done in the same pass)

- [x] 2.1 101 non-fitting text sidecars deleted from `corpus/texts/` (92) and `corpus/personal_library/` (9)
- [x] 2.2 24 triplets referencing removed items auto-rejected with `triplet_verdict: reject-layout` and reason `"auto: references items removed for gallery-text zone fit — ..."`
- [x] 2.3 Manifest checked — zero entries removed (text sidecars aren't tracked in manifest; inline `text`/`text_variants` live in git only)

## 3. Spec

- [x] 3.1 Add "Text body fits gallery-text zone" requirement to `corpus-ingestion` spec delta
- [x] 3.2 `openspec validate require-text-items-fit-zones` passes

## 4. Out of scope

- Rebuilding the 24 dangling-ref triplets; they're dead weight but harmless.
- Generalizing the rule across faces (no other face's text zone has an item-level form/zone mapping — `delight_text`, `hn_title`, `poetic_line`, etc. are all scoped to specific face components, not to the item taxonomy).
- Re-ingesting the deleted items with proper line breaks; that's a separate authoring/fetching pass. If we want them back, they need a clean `ingest-personal` batch that passes the validator.
