# Archival note — 2026-04-27

This change proposed a 30-day deliberate review of generated pairings
(operator + spouse) culminating in a written GO / MODIFY / DROP
verdict, used as a gate for `add-pairing-pipeline`.

**Verdict, retroactive: GO.**

The motivating question was "can pairing work?" — i.e., does the
tag-based retrieval algorithm produce coherent triplets that read as
intentional rather than random. That question was answered post-hoc by
the existence of a hand-curated triplet pool that already passes
review:

- `corpus/_triplets/*.yaml` contains 1,023 ratified triplets as of
  2026-04-25 (commit `595057f` — *"Picker: regenerate triplet pool
  (868 → 1023, wrap-aware gate applied)"*).
- Each triplet has been through `corpus_review.py` review with an
  explicit `triplet_verdict: keep | reject-content | reject-layout`
  field — i.e., the operator (and, where relevant, the spouse) has
  already reviewed each one against the rendered Summary / Gallery /
  Night faces.
- The daily rotation has been live in production through April 2026
  with no "this pairing makes no sense" complaints.

The original experiment design (generate 30 days, render two-panel PDF,
sit-down review session, write `verdict.md`) was never run because the
authoring workflow turned out to be more thorough — every triplet is
reviewed at authoring time, not in batch. The PDF artefact was
unnecessary; the in-browser review tool (`corpus_review.py`) covers the
same ground per-triplet with renderer-rendered previews instead of
PDF-flattened ones.

Archived. The blocking dependency on `add-pairing-pipeline` is lifted
(`add-pairing-pipeline` is itself in flight as a future iteration; see
its own ARCHIVAL-NOTE.md for status).
