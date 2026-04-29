# Tasks

- [ ] Operator reviews `lists/four-line-stanzas.yaml`, marks per-entry verdicts
      (`approved`, `swap`, `drop`), and signs off on bucket counts.
- [ ] **Locate or recreate the smart_pill prompt** — not in the repo. Either
      retrieve the operator's saved prompt or reverse-engineer from the 146
      existing corpus pills (claude-haiku-4-5, ~440 chars target, Wikipedia
      sources, deep-dive style). Commit to `pairing/prompts/smart_pill.md`
      so regeneration is reproducible.
- [ ] **Build `pairing/corpus_generate_pills.py`** — takes a list of text ids
      (or `--all-missing`), loads each sidecar, calls Anthropic API with the
      saved prompt + body + author/title, writes back `smart_pill: { body,
      sources, generated_at, model }`. Trim/regen if response > 440 chars.
- [ ] For approved entries: run `corpus fetch-list lists/four-line-stanzas.yaml`
      to ingest bodies + author sidecars. Each text MUST emerge from this
      pass with both `text_variants` and `smart_pill.body` populated — pill
      generation is part of the single ingestion pass, not a follow-up.
- [ ] Run `corpus validate --full` to confirm every new entry passes structural
      + manifest checks and the orientation-aware resolution floor (n/a for
      texts) and the picker's `wrapped_visual_lines ≤ 4` constraint. Validator
      MUST also enforce `smart_pill.body` present and ≤440 chars.
- [ ] Re-run the triplet generator (`corpus_build_triplets_v2.py --apply`) and
      confirm the summary-pool size grew by ~100 and the picker hits 1023
      triplets without exhausting `max_attempts`.
- [ ] Audit theme coverage (compare orphan-image counts before/after) and
      confirm the underused subject themes targeted in the proposal now
      have summary-side representation.
- [ ] Archive the change once all entries are committed and validation passes.
