## Why

The pairing concept — Gallery's hero and Summary's delight as a daily thematically-linked duet — is the project's soul. It may also be the feature most likely to flop in practice. People notice connections they were primed to look for; they easily miss a pairing shown in different zones at different times of day.

Committing to the full pairing pipeline (daily orchestration, month-shuffled calendar, mood/register intersection, pre-generation) without validating the concept is expensive: implementation of `add-pairing-pipeline` plus downstream wiring is nontrivial, and backing out gracefully after shipping would require reverting both the code and a live habit of daily curation.

This change is a deliberate viability test. It produces 30 days of pairings against the v1 seed corpus, renders them as a single reviewable document, and has the operator (and importantly, the wife) look at it. If the pairings land, the full pipeline proceeds. If they don't land, the pipeline either changes shape (theme-only rotation without companion-linking) or disappears entirely.

## What Changes

- Build a standalone Python script that generates 30 days of pairings using the ratified tag-based retrieval + mood/register intersection algorithm, against the current `corpus/` state.
- Render each day's pairing as a two-panel PDF page: the Gallery face (visual-day or text-day as chosen) on the left, the Summary face on the right (with its delight zone populated by the companion).
- Produce a single PDF document containing all 30 days, plus a short review guide and a structured feedback form at the back.
- Conduct a **pairing review session** with the operator (and wife) where each day is looked at, pairings are rated, notes are captured.
- Produce a **viability verdict** based on the review: **GO** (pairing pipeline proceeds as designed), **MODIFY** (specific design changes identified, re-run experiment), or **DROP** (the pairing concept is abandoned; Gallery and Summary independently rotate within theme).
- Record the verdict in a `verdict.md` document in this change's directory, to be referenced by subsequent changes.

## Capabilities

### New Capabilities

None — this change produces an artifact (the verdict) and a decision, not a new runtime capability. It does not add to the `openspec/specs/` set when archived; it archives with a verdict and an empty spec directory (or a reserved placeholder).

### Modified Capabilities

None in the normative sense. The verdict may inform the content of `add-pairing-pipeline`, but does not modify a ratified spec here.

## Impact

- **Dependencies**: requires `add-corpus-schema` and `add-corpus-ingestion` applied, and `build-seed-corpus` at the v1 milestone (300+300 items, every theme ≥15 per side). This is the soonest point at which pairings have a real chance of looking good.
- **Uses**: the rendering pipeline (`add-rendering-pipeline`) and dashboard faces (`add-dashboard-faces`) must be available to render the review PDF's panels. Alternative: use a standalone renderer one-off for this experiment. The specs leave this choice to the implementation, but the preference is to use the real rendering so the review is faithful.
- **Produces**: one PDF (`openspec/changes/experiment-pairing-viability/review.pdf`, not committed — regenerated on each run), one verdict document (`verdict.md`, committed).
- **Blocks**: `add-pairing-pipeline` cannot archive until the verdict is **GO** or **MODIFY**-with-changes-applied.
- **No runtime impact**: this is an offline experiment; nothing it produces runs on the device.
