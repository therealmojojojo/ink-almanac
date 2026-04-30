# Proposal: Picker coverage fix

## Motivation

Audit found that of the corpus's 1,176 image sidecars, only **292 (25%)** appear
in any triplet — and of those 292, the same items recur up to 5 times each.
Of 664 text sidecars, 65 (10%) are similarly never used. Four independent
mechanisms in `corpus_build_triplets_v2.py` produce this:

1. **`corpus/images/` is not scanned**. v2's `load_items()` walks only
   `("texts", "personal_library")`, dropping the 119 PD print sidecars
   (Dürer, Rembrandt, Piranesi, Hokusai, Beardsley, Goya, Whistler, Blake,
   Daumier, Munch, …) that the `2026-04-19-add-bw-graphic-arts-canon` change
   was specifically built to introduce as the non-photograph spine. v1
   included `"images"`; v2 dropped it without a documented rationale. This
   is treated as a regression.
2. **Per-item cap of 5**. With ~442 anchors × 5 + ~352 summaries × 5
   capacity, the picker reuses popular items up to 5 times instead of
   exhausting the long tail.
3. **Pure-random selection over the available pool**. With `random.choice`
   over the eligible set, items with broader theme overlap dominate; rarer
   items (long tail) almost never get drawn before max_attempts exhausts.
4. **Summary-pool gate is stale**. The picker filters summary candidates
   with `wrapped_visual_lines(body, 24) ≤ 4` and the validator caps
   `delight_text` at `24 chars × 4 lines`. Both numbers were correct under
   the pre-tier-ladder renderer but never re-derived after `summary.ts`
   was reworked to the metric-driven `pickFitTier` algorithm
   (Phase 1 ≥28u unwrapped → Phase 2 28u with hanging-indent →
   Phase 3 sub-pill 24u/22u escape). The current renderer's pill-parity
   floor is 28u with a soft-cpl of 44 and max-visual-lines of 12; the
   picker's 24×4 gate rejects roughly 6× the content the renderer
   actually accepts. Empirical check on the 43-entry famous-quotes
   review set: only 7 pass the picker's gate, but all 43 land at
   pill-parity (≥28u) under `pickFitTier`. Three sources of truth all
   need to be re-anchored to the renderer:
   - `openspec/specs/dashboard-faces/spec.md` zone-budget table row
     for `delight_text` (still 24×4)
   - `pairing/corpus_validate.py` constants `SUMMARY_DELIGHT_MAX_CHARS`
     and `SUMMARY_DELIGHT_MAX_LINES` (still 24, 4)
   - `pairing/corpus_build_triplets_v2.py` constants `SUMMARY_WRAP_COLS`
     and `SUMMARY_MAX_VISUAL_LINES` (still 24, 4)

   The `corpus-schema` spec already documents the post-rework cap as
   "≤14 visual lines after wrap, in a 552u-wide cell" — that line is
   correct; the others drifted.

## What changes

1. **Re-include `corpus/images/`** in `load_items()`'s folder list. Restores
   the 119 PD print canon to picker eligibility.
2. **Cap 5 → 3** (`PER_ITEM_CAP = 3`). Halves average reuse without breaking
   the math: at cap=3, the summary pool of 352 supports up to 1,056
   triplets, comfortably above current 1,023.
3. **Two-pass generation** in `generate()`:
   - **Pass 1 — coverage**: every eligible item used at most once. Walks
     anchors / summaries / galleries with `use[id] == 0` filters; theme
     constraints unchanged. Caps out when no new unique-item triplet is
     possible.
   - **Pass 2 — fill**: continues to the target with coverage bias. The
     `avail()` helper now returns only items at `min(use[id])` within the
     eligible pool, so use=0 items are picked before use=1, etc. Random
     pick within the min-use subset preserves fairness.
4. **Triplet target derived from pools**: `target = min(anchor_pool,
   summary_pool) * PER_ITEM_CAP`. With the current pools and cap=3, that's
   1,056 — within reach of (matching) the existing 1,023 production count.
5. **Re-anchor the summary-pool gate to the renderer**.
   - **Spec**: update the `delight_text` row in the dashboard-faces
     zone-budget table from `24 / 4` to `44 / 12` (the tier-4/5
     pill-parity numbers from `pickFitTier`), with a note pointing at
     `summary.ts:pickFitTier` and naming the tier-7 `57 / 13` sub-pill
     escape as a relief valve, not a default.
   - **Picker** (`corpus_build_triplets_v2.py`): replace the
     `wrapped_visual_lines(body, 24) ≤ 4` filter with a Python port of
     `pickFitTier`. The gate becomes "the candidate's body lands at
     tier 1–5 (pill-parity, ≥28u)". The Python port lives next to the
     existing `wrapped_visual_lines` helper and mirrors the TS tier
     table verbatim; a comment in both files names the other as the
     mirror so future drift is caught at review.
   - **Validator** (`corpus_validate.py`): retire
     `SUMMARY_DELIGHT_MAX_CHARS` and `SUMMARY_DELIGHT_MAX_LINES` as
     hard structural rules. Replace with a softer warning when an item
     marked `summary_eligible: true` (or default) lands at tier 6 or 7
     under `pickFitTier` — i.e. the renderer can fit it, but only via
     the sub-pill escape.

## Expected end state

| metric | current | after |
|---|---:|---:|
| triplets | 1,023 | ~1,500–1,800 |
| distinct anchor texts | 442 / 442 (100%) | 442 / 442 (100%) |
| **summary-eligible pool** | **~352** | **~500–550** |
| distinct summary texts | 342 / 352 (97%) | ~500+ / ~520 (≥95%) |
| distinct gallery-text refs | 214 / 276 (78%) | ~270+ / 276 (≥98%) |
| **distinct gallery-image refs** | **292 / 1,161 (25%)** | **~900–1,000 / 1,280 (≥75%)** |
| max reuse per item | 5 | 3 |

The summary pool grows because mechanism 5 admits items the renderer
already lays out cleanly at ≥28u (Phase 2 with `.wrap-turnover`
hanging-indent). On the 43-entry famous-quotes review set the gate
flips from 7 admitted → 43 admitted; extrapolated across the corpus
the pool is expected to grow by ~50%. That in turn lifts the triplet
target (mechanism 4: `min(anchor_pool, summary_pool) * PER_ITEM_CAP`),
which in turn reduces the summary-pool-bound gap on gallery-image
coverage. The numbers above are projections; the apply step in the
task list confirms or adjusts them.

The gallery-image upper bound shifts because (a) the pool grows by 119
with the PD prints rejoining (mechanism 1), (b) the two-pass + coverage
bias forces every matchable item into rotation at least once before any
item gets a third use (mechanism 3), and (c) the larger summary pool
(mechanism 5) raises the triplet target so more gallery slots are
filled.

## Out of scope

- Theme-match fallback ladder (proposed earlier) — quality tradeoff,
  separate change.
- Rolling diversity / era / author constraints across the rotation —
  quality-of-rotation work, separate change.
- Operator metadata sweep on the 8 PL images with empty post-strip
  dominant themes and the 7 with orphan dominant themes — operator-side
  YAML edits, tracked separately.
- Adding new content to the summary pool — `expand-summary-pool` covers
  the anthology-list ingestion lever, separate from this gate-alignment
  change. Both can land independently; together they compound (more
  content × more permissive gate).
- Replacing the renderer's `pickFitTier` algorithm or its tier table —
  this change only mirrors the existing renderer behavior into the
  picker and validator. Tier-table tuning is a renderer change.
