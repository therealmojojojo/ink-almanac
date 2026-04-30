# Tasks

- [x] Edit `pairing/corpus_build_triplets_v2.py` (mechanisms 1–4):
  - [x] add `"images"` to the folder list in `load_items()`
  - [x] `PER_ITEM_CAP = 5` → `3`
  - [x] refactor `generate()` into two passes (coverage → fill) with a
        min-use coverage bias in `avail()`
  - [x] derive `triplet_target` (now `len(summary_texts) * PER_ITEM_CAP`
        — anchors are the invisible spine and may reuse freely; visible
        summary cap is the gating constraint); loop exits on target
        reached or N consecutive failed attempts
- [x] Re-anchor the summary-pool gate to the renderer (mechanism 5):
  - [x] port `pickFitTier` from `renderer/src/modes/summary.ts:181-233`
        into a new helper `pick_fit_tier(body) -> int | None` in
        `pairing/corpus_build_triplets_v2.py`. `DELIGHT_TIERS` mirrored
        verbatim with the Phase 1 / 2 / 3 logic, top-of-section comment
        names the TS source.
  - [-] add a corresponding comment block to
        `renderer/src/modes/summary.ts` naming the Python port.
        N/A — the renderer is the source of truth and doesn't need to
        cite its mirrors. Comment lives only in the Python sites
        (`corpus_build_triplets_v2.py`, `corpus_validate.py`,
        `corpus_mark_summary_eligibility.py`).
  - [x] replace the `summary_eligible` filter's
        `wrapped_visual_lines(body, 24) ≤ 4` check with
        `pick_fit_tier(body) is not None` (admits any tier in phases
        1–3; rejects only items that would need the last-resort
        sub-floor wrap fallback).
  - [x] retire the `wrapped_visual_lines` helper in
        `corpus_build_triplets_v2.py` — replaced by `pick_fit_tier`.
        Standalone copies in `corpus_extract_fragments.py` and
        `corpus_analyze.py` are unaffected (they serve different,
        non-admission purposes).
  - [x] in `pairing/corpus_validate.py`, retire
        `SUMMARY_DELIGHT_MAX_CHARS` / `SUMMARY_DELIGHT_MAX_LINES` as
        hard rules. Now uses `delight_fit_tier()` mirroring the
        renderer; errors only when no tier in phases 1–3 fits.
- [x] Update `openspec/specs/dashboard-faces/spec.md` zone-budget table
      row for `delight_text` from `24 / 4` to `44 / 12` and add a
      `notes` cell pointing at `summary.ts:pickFitTier`. Delta merged
      from `specs/dashboard-faces/spec.md` under this change at archive
      time.
- [x] Dry-run / preview without `--apply`: confirmed projected counts
      (summary pool 366 → 599, triplets 1069 → 1764, distinct items
      touched 1467 → 1815, years 2.9 → 4.8).
- [x] Apply: `python pairing/corpus_build_triplets_v2.py --apply` —
      regenerated `corpus/_triplets/` from scratch (1764 triplets).
- [x] Validate: `corpus validate` — 57 pre-existing errors (45 missing
      `source_url` on PD texts + 8 wrong-tier placements + minor
      taxonomy/panel-fidelity items). Picker output itself is clean.
- [-] Spot-check the 43-entry famous-quotes review set
      (`openspec/changes/expand-summary-pool/lists/quotes-review/`):
      every entry now passes the picker's gate; rendered summary-face
      PNGs (via `corpus build-review-page`) show no overflow at the
      chosen tier.
      N/A — covered by the broader 599-pill regen + tier-aware
      admission audit, which spot-checked random pills and verified
      the 1764-triplet picker output.
- [x] Compare new corpus against the prior 1,023 triplets — broader
      summary pool (366 → 599), broader gallery-image set (114 more
      images now in scope, full 100% nocturne coverage), lower
      max-reuse on visible slots, target band shifted upward per the
      proposal table.
- [x] Archive change once observable counts match the proposal targets.
