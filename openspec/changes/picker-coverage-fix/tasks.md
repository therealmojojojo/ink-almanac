# Tasks

- [ ] Edit `pairing/corpus_build_triplets_v2.py` (mechanisms 1–4):
  - [ ] add `"images"` to the folder list in `load_items()`
  - [ ] `PER_ITEM_CAP = 5` → `3`
  - [ ] refactor `generate()` into two passes (coverage → fill) with a
        min-use coverage bias in `avail()`
  - [ ] derive `triplet_target = min(anchor_pool, summary_pool) *
        PER_ITEM_CAP`; loop exits on target reached or N consecutive
        failed attempts
- [ ] Re-anchor the summary-pool gate to the renderer (mechanism 5):
  - [ ] port `pickFitTier` from `renderer/src/modes/summary.ts:181-233`
        into a new helper `pick_fit_tier(body) -> int` in
        `pairing/corpus_build_triplets_v2.py`. Mirror the
        `DELIGHT_TIERS` table verbatim (tier, font, line-height,
        soft-cpl, max-visual-lines) and the Phase 1 / 2 / 3 logic. Add
        a top-of-file comment naming the TS source as the mirror.
  - [ ] add a corresponding comment block to
        `renderer/src/modes/summary.ts` naming the Python port.
  - [ ] replace the `summary_eligible` filter's
        `wrapped_visual_lines(body, 24) ≤ 4` check with
        `pick_fit_tier(body) in (1,2,3,4,5)`.
  - [ ] keep the existing `wrapped_visual_lines` helper for any
        non-summary use and mark with a comment that it is no longer
        the admission gate.
  - [ ] in `pairing/corpus_validate.py`, retire
        `SUMMARY_DELIGHT_MAX_CHARS` / `SUMMARY_DELIGHT_MAX_LINES` as
        hard rules. Replace with a soft warning when an item with
        `summary_eligible: true` (default included) lands at
        `pick_fit_tier == 6` or `7` — fits via the sub-pill escape,
        but the operator should know.
- [ ] Update `openspec/specs/dashboard-faces/spec.md` zone-budget table
      row for `delight_text` from `24 / 4` to `44 / 12` and add a
      `notes` cell pointing at `summary.ts:pickFitTier` and naming the
      tier-7 sub-pill escape (`57 / 13`) as a relief valve. (Delta
      lives in `specs/dashboard-faces/spec.md` under this change.)
- [ ] Dry-run / preview without `--apply`: confirm projected counts
      (summary-pool size, distinct items per slot, max-use distribution).
- [ ] Apply: `python pairing/corpus_build_triplets_v2.py --apply` —
      regenerates `corpus/_triplets/` from scratch.
- [ ] Validate: `corpus validate` passes; any tier 6/7 warnings are
      reviewed and either accepted or the entry is rewritten / marked
      `summary_eligible: false`.
- [ ] Spot-check the 43-entry famous-quotes review set
      (`openspec/changes/expand-summary-pool/lists/quotes-review/`):
      every entry now passes the picker's gate; rendered summary-face
      PNGs (via `corpus build-review-page`) show no overflow at the
      chosen tier.
- [ ] Compare new corpus against the prior 1,023 triplets — broader
      summary pool, broader gallery-image set, lower max-reuse, target
      band shifted upward per the proposal table.
- [ ] Archive change once observable counts match the proposal targets.
