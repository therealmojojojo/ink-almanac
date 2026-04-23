## Why

Gallery text-day renders a text item's body into one of four form-specific zones (`haiku_body`, `poem_body`, `aphorism_body`, `quote_body`, per `renderer/src/zones.ts`). Each zone has a hard budget: `maxChars` × `maxLines`. The renderer enforces the budget at HTTP boundary by returning `VERSE_OVERFLOW` for over-budget inputs — the PNG is never produced and the face is broken.

Until now, enforcement only ran when a text was referenced as a triplet slot. Items could exist in the corpus that could never be used — their body overflowed the zone for their declared form. An audit of the 203 text items in the corpus found **101 (50%)** that would overflow at render:

- **23** line-width overflows (single lines longer than the zone's maxChars) — most of these are ingestion bugs: the body was stored as one very long line because verse breaks were stripped during fetch/parse (e.g., the Eminescu cluster, `kafka-before-the-law`, `ponge-bread`/`ponge-the-crate` all at identical 259- or 329-char widths).
- **16** line-count overflows over the form's hard maxLines (`cosbuc-nunta-zamfirei` 335 lines as `stanzaic`, `cosbuc-mama` 127 lines, `keats-ode-grecian-urn` 61 lines, etc.).
- **48** fit hard budgets but exceed the 16-line practical 2-column cap for `poem_body` forms — these render but overflow vertically, signalling failure by visible clip on the Gallery face.
- **3** hit both line-count AND line-width.
- **11** had forms outside the closed taxonomy (`haiku`/`tanka`/`sonnet`/`free-verse`/`stanzaic`/`fragment`/`prose-poem`/`aphorism`/`quote`) — these couldn't have been routed to any zone at all.

The pool was cleaned: the 101 non-fitting items were deleted; 24 triplets that referenced them were auto-rejected for dangling refs. The remaining 102 text items all fit.

This change ratifies that state: **a text item is ingested only if its body fits its form's gallery-text zone budget, and it never overflows the practical 2-column vertical cap.** The validator is the enforcement point for both re-ingestion (`corpus ingest-personal --commit`) and periodic audit (`corpus validate`).

## What Changes

- Adds one requirement to `corpus-ingestion`: text body fit.
- `pairing/corpus_validate.py`'s `validate_text` grows a body-fit check against the form's zone budget plus the 16-line practical 2-col cap for `poem_body` forms. Items with forms outside the gallery-text taxonomy are rejected.
- Budget constants live at module top with a comment tying them to `renderer/src/zones.ts` and `renderer/src/modes/gallery.ts` (`FORM_TO_ZONE`). These must be kept in sync when the zone table is retuned.
- Rejected triplets are skipped by triplet integrity checks (their dangling refs no longer produce validation errors) — they stay in the repo as a record but aren't held to live-pool invariants.

## Capabilities

### Modified Capabilities

- `corpus-ingestion`: adds the "Text body fits gallery-text zone" requirement.

## Impact

- **Spec**: one new requirement in `openspec/specs/corpus-ingestion/spec.md` after archive.
- **Validator**: new item-level check; the corpus presently passes (after the 101-item cleanup and rejected-triplet skip). 0 errors, 374 warnings (long-edge preferences, non-blocking).
- **Staging pipeline**: `corpus ingest-personal --commit` invokes the validator before moving files out of `_staging/`, so new texts that don't fit fail commit the same way the existing `rights_tier` / `panel_fidelity` checks already fail.
- **Rebuild work**: 24 triplets now have `reject-layout` verdicts with reason `"auto: references items removed for gallery-text zone fit — ..."`. Those are out of the active pool and won't render. Rebuilding them is a separate authoring pass.

## Relationship to other changes

Sibling of `require-slot-orientation` and `require-summary-text-fits-zone`. All three say "slot content must honor its rendering zone"; this one operates at the item boundary (ingestion) rather than at the triplet boundary. Could fold into a single "zone fit" change in a future consolidation.
