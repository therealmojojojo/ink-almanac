# Tasks

- [-] Operator reviews `lists/four-line-stanzas.yaml`, marks per-entry verdicts
      (`approved`, `swap`, `drop`), and signs off on bucket counts.
      N/A — superseded. The buffer goal (lift summary pool above the 10-text
      cushion) was achieved via tier-aware admission instead. The 100-stanza
      list remains in this archived change folder for future re-use if the
      under-represented themes (`architecture-and-structure`,
      `interior-and-domestic`, `childhood-and-play`, `rural-pastoral`,
      `night-and-lamplight`, `ritual-and-gathering`, `machines-and-mechanisms`)
      need filling.
- [x] **Locate or recreate the smart_pill prompt** — built as
      `pairing/corpus_generate_pills.py:PROMPT_A` (word-focus) and
      `PROMPT_B` (whole-piece) plus GUARDRAILS and VOICE_AND_OUTPUT
      blocks. Subsequently rewritten as a simpler prompt with a
      tier-aware word-mode option (kitchen-counter friend voice).
- [x] **Build `pairing/corpus_generate_pills.py`** — committed in
      `e88e0b6`. Caches the system block, retries with extraction
      tolerance, falls back across `claude-opus-4-7` →
      `claude-opus-4-5` → `claude-opus-4-1`.
- [-] For approved entries: run `corpus fetch-list lists/four-line-stanzas.yaml`
      to ingest bodies + author sidecars.
      N/A — superseded by the broader pill-regen + tier-aware admission
      route. The stanza list was never approved or ingested.
- [x] Run `corpus validate --full`. Result: 57 pre-existing errors
      (45 missing `source_url` on PD texts + 8 wrong-tier placements +
      minor taxonomy/panel-fidelity items) — all pre-date this change
      and are tracked as separate corpus-authoring debt.
- [x] Re-run the triplet generator (`corpus_build_triplets_v2.py --apply`).
      Result with tier-aware admission: 599 summary pool, 1764 triplets,
      4.8 years of daily content, 100% nocturne saturation, ~90% gallery
      image coverage at 60/40 split.
- [x] Audit theme coverage. Random-sample audit of 10 newly-regenerated
      pills confirmed strong coverage across forms and tiers; voice
      formulas (`the move is`, `re-read`) dropped from 55% / 81% of the
      pool to 0% in the regenerated pool.
- [x] Archive the change.

## Outcome notes

The proposal's *literal* scope (ingest 100 specific stanzas) was not
executed. The proposal's *underlying motivation* (lift the summary buffer
beyond the 10-text cushion) was met by a different mechanism: aligning
the picker's eligibility filter with the renderer's `pickFitTier` ladder
instead of the artificial 24cpl / 4-line proxy. The summary pool grew
from 352 → 366 → **599** — a 247-text headroom over the original 342
floor.

The 100-stanza list (`lists/four-line-stanzas.yaml`) remains intact in
this archived change folder. If a future change needs to fill the
under-represented themes the proposal targeted, that list is the natural
starting point.
