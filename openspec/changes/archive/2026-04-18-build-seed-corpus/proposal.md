## Why

The dashboard cannot function without a real corpus. The schema is defined and the ingestion tooling will be built, but neither is useful until actual images and texts land in `corpus/` with validated sidecars. This change is where the operator sits down and assembles the seed corpus through a planned sequence of **canonical lists** — one per category — and where the mood and register vocabularies finally confront real items and stop drifting.

This is explicitly a long-running, human-in-the-loop change. Other work can proceed in parallel; it only blocks `experiment-pairing-viability`.

The approach is **anthology-first, not discovery-first**: because the target corpus is small (a few hundred items per side), every item might as well be drawn from the canon. For each category — a poet, a photographer, a series, an anthology section — the operator approves a named list of works up front, and `fetch-list` executes it.

## What Changes

The seed corpus now builds in **two phases**:

### Phase 1 — Item pool

- Plan and execute ingestion as a sequence of **canonical-list batches**, one per category, so the item pool grows along curatorial lines rather than accidental ones.
- Reach the item-pool target: at least **200 images + 200 texts**, with every theme having at least **10 applicable items per side** (image or text). The pool is deliberately smaller than originally planned because items are reused across many triplets — a single Hokusai print may anchor ten different days without feeling repetitive because the *composition* (triplet) is what rotates, not the item.
- Source PD items across the Tier-1 PD channels (Met, Rijksmuseum, Gallica, LoC, Project Gutenberg, Wikisource, Wikimedia Commons).
- Source personal-library items via the web-search channel established by `add-corpus-ingestion` (Brumaru, Dinescu, Cartier-Bresson, Doisneau, Iancu, Warhol, Hopper, etc.). When web reproductions are insufficient at acceptable quality, substitute a comparable work or drop the item; there is no scanning path.
- Propose, review, and ratify all vocabulary amendments needed as real items stress-test the mood and register sets. Amendments flow through their own dedicated change proposals, not this one.
- Reach vocabulary stability: two consecutive canonical-list batches complete without amending `mood.yaml` or `register.yaml`.
- Ensure the item pool contains enough anchor-eligible short forms to support triplet authoring in Phase 2 — target at least **80 anchor-eligible text items** (`haiku`, `aphorism`, `fragment`, `quote`, `song-chorus`, `lyric`) within the 200-text pool.
- The corpus deliberately has **no personal-library ceiling**: given the operator's taste (heavy in 20th-century poetry and photography), personal-library is expected to be the majority tier on both sides, and that is fine under the private-use posture established by the schema.

### Phase 2 — Triplet authoring

- Plan and execute triplet authoring as a sequence of batches via `corpus propose-triplets` → `corpus review-triplets` → `corpus commit-triplets`, using the Phase-1 item pool as the source pool.
- Reach the triplet-pool target: at least **300 committed triplets** spanning a mix of visual-day and text-day flavors, with aligned-nocturne where curation allows.
- Target **flavor mix**: approximately 60% visual-day triplets and 40% text-day triplets across the committed pool.
- Target **aligned-nocturne coverage**: at least **40% of triplets** (~120 of 300) carry an `aligned_nocturne`; the remaining 60% rely on the general nocturne pool. This is a soft target — quality beats coverage.
- Produce a coverage audit at the final milestone including both item-pool coverage (by theme, by flavor, by tier) and triplet-pool coverage (by theme, by flavor, by aligned-nocturne share).

## Capabilities

### New Capabilities

- `corpus-seed`: The process, targets, and gating criteria for assembling the initial corpus. This capability owns the coverage commitments, the milestone definition, and the audit format. It is an operational capability — its specs describe targets and gates, not code.

### Modified Capabilities

None. Vocabulary amendments proposed during this change modify `corpus-taxonomy` through their own dedicated change proposals (per the amendment procedure), not through this one.

## Impact

- **New files during execution**: ~600 sidecars under `corpus/images/`, `corpus/texts/`, `corpus/nocturne/`, `corpus/personal_library/`; corresponding entries in `corpus/_manifest.json`; binaries and personal-library body files on disk (not in git); canonical list files under `openspec/changes/build-seed-corpus/lists/`.
- **Vocabulary churn during execution**: amendments to `corpus/_taxonomy/mood.yaml` and `corpus/_taxonomy/register.yaml` expected early, tapering to zero before archive.
- **Operator time**: realistic estimate ~20 canonical lists × ~30 items per list = 600 items, with taste decisions concentrated at list-approval time (a minute or two per list entry) and corrections at contact-sheet pruning time (seconds per banned item). Probably 4–10 hours of operator attention total, spread over weeks.
- **Claude API cost**: approximately $20–40 over the full seed, dominated by list-proposal calls (each proposal call includes the full taxonomy but runs once per list, not once per item).
- **Storage**: ~2–8 GB of binaries and body files on disk plus external backup, depending on resolution choices.
- **No code**: this change produces data, not code. Specs describe gates and audit format; tasks describe the operational workflow of list proposal, fetch, prune, and audit.
