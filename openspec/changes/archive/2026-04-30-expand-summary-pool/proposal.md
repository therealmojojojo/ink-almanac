# Proposal: Expand the summary-eligible text pool by 100 short stanzas

## Motivation

The picker's summary-slot pool is the choke point in the corpus. After the
recently-validated cap reduction (5 → 3 per item) the pool needs ~342 distinct
summary-eligible texts to fill 1023 triplets without strain; the current corpus
yields 352 — a 10-text buffer. Any churn (a few summaries falling out of the
≤4 visual-line eligibility on a future picker tweak, a few new triplets) can
push the picker over the edge and force the summary pool to be re-used at the
cap.

Adding 100 short stanzas (≤4 visual lines under the picker's 24-col wrap)
raises the buffer to ~110 and unlocks broader theme coverage in the summary
slot, which is the hinge for matching summary→gallery image pairs in
`corpus_build_triplets_v2.py`.

## Scope

- 100 candidate items, anthology-first, drawn from canonical poetry across
  English, Romanian, French, German, Persian, Chinese, with PD-priority
  where source allows.
- All entries vetted at list-time for the picker's eligibility constraint:
  `wrapped_visual_lines(body, 24) ∈ (0, 4]`.
- All entries pre-tagged with subject themes (post-strip), prioritising
  themes currently underused in the summary pool: `architecture-and-structure`,
  `interior-and-domestic`, `childhood-and-play`, `rural-pastoral`,
  `night-and-lamplight`, `ritual-and-gathering`, `machines-and-mechanisms`.

## Workflow (anthology-first governance)

1. **List approval**: operator reviews `lists/four-line-stanzas.yaml`,
   strikes/swaps entries, weights bucket distribution.
2. **Ingestion**: per the existing convention, `corpus fetch-list` walks
   approved entries, fetches the body from `source_url`, and authors a
   full sidecar in one pass per item (no operator TODO-filling).
3. **Validation**: every ingested sidecar must pass `corpus validate` and
   `wrapped_visual_lines ≤ 4` for the EN body before commit.

## Out of scope

- No changes to the picker logic.
- No changes to `text_variants` schema or other corpus tooling.
- No spec changes — this is a content addition, not a capability change.
