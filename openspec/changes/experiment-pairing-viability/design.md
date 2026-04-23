## Context

Spec-driven development optimizes for clarity of intent. It does not substitute for testing the most uncertain design decisions before committing to implementation. The pairing concept has been argued in conversation — visual-day and text-day flavors, hero/companion roles, mood/register intersection — and the arguments feel right on paper. They may not feel right in a kitchen. This change is the deliberate gap between "reasoned-about" and "ratified."

The structure is deliberately lightweight: generate 30 days, print them, look at them together, decide. The experiment is cheap; the downstream change (`add-pairing-pipeline`) it gates is expensive. The cost-benefit favors running the experiment.

## Goals / Non-Goals

**Goals:**
- Produce an honest judgment about whether the pairing concept works, before the full pipeline is built.
- Capture *why* it works or doesn't — not just a yes/no but patterns (text-day stronger than visual-day, certain themes fail, companion mood-axis too loose, etc.).
- Make DROP psychologically safe. The experiment exists to allow "no."

**Non-Goals:**
- Running the real daily-generation pipeline. A standalone script is enough.
- Scale testing. 30 days against v1 seed is the minimum viable sample.
- Production-quality rendering. Review panels at reduced size are fine.
- Statistical rigor. This is a taste test, not a randomized trial.

## Decisions

### 30 days, one deliberate month

30 is the smallest sample that covers the full theme rotation (or nearly — the experiment can cycle through a shuffled month-length sequence of themes). It's also manageable for a single review session. Smaller samples (7 days, 14 days) risk being dominated by a few lucky or unlucky picks; larger samples (60, 90) push the review into multiple sessions and reduce signal-to-noise.

### Review at v1 corpus, not final

v1 (300+300) is enough diversity to see whether pairings work. Waiting for final (1000+1000) delays the gate without improving it — if v1 pairings fail, final pairings are unlikely to save the concept. If v1 pairings succeed, the larger corpus only adds safety margin.

### A PDF, not a web page

Rationale: the review is deliberate, focused, co-located with another person. A printed or full-screen PDF invites slow attention; a web page invites scrolling and distraction. The PDF is also naturally archivable alongside the verdict document.

### Verdict committed; PDF not committed

The PDF regenerates on each run and is ephemeral. The verdict is the durable record. Committing the PDF would pollute the repo (6 × 30 pages of images) without benefit; committing the verdict preserves the decision's accountability.

### MODIFY as a first-class outcome

It would be cleaner to reduce the verdict to GO / DROP. But the expected realistic outcome is MODIFY — "pairings work in text-day but feel forced in visual-day," or "mood intersection needs ≥3 shared tags not ≥2." Making MODIFY explicit forces the review to capture the specific change, and lets `add-pairing-pipeline`'s specs be amended before applying.

### The wife is listed as a participant

She is the stated quality bar. Noting her role here makes the review honest and the verdict meaningful. If she doesn't notice the pairings, that's important data.

### The experiment is itself a throwaway

No runtime capability is added. `specs/pairing-viability/spec.md` exists only to satisfy OpenSpec's artifact schema (specs are required); it describes the experiment's behavior, not an ongoing feature. After archive, this capability is historically interesting but functionally inert.

## Risks / Trade-offs

- **Corpus quality dominates pairing quality.** If the v1 corpus is thin on a theme or has poorly-tagged items, pairings drawn from that theme will suffer. The review must distinguish "the pairing concept fails" from "this corpus has a hole." Mitigation: the feedback form captures patterns per theme, not just global counts.

- **Review fatigue.** 30 two-panel pages is 60 images to process. Plan for two sessions of 15 days each if the first session feels taxing.

- **Confirmation bias.** Operator and wife may want the concept to work. Mitigation: an explicit "not working" column in the feedback form, reviewed after all pages are marked (not during). Disagreements between operator and wife should be noted rather than averaged.

- **Single 30-day run is a small sample.** A pattern visible in one month may be an artifact. Mitigation: if the first run is MODIFY with an interesting signal, run a second 30-day with the modification applied. Still cheap.

- **Archival ambiguity.** If the verdict is DROP, archival should be clean. Current design supports this — the change archives with the verdict document; no downstream specs move forward. If the verdict is MODIFY, archival should wait until `add-pairing-pipeline`'s specs are amended accordingly. That's an operator-discipline risk, not a process one.

## Migration Plan

No prior experiment exists. On apply:

1. Wait for `build-seed-corpus` to hit v1.
2. Implement the standalone generation script (calls into the corpus, runs the retrieval algorithm, produces today.json-shaped outputs for 30 days).
3. Implement the PDF renderer (uses the real rendering pipeline for each Gallery/Summary face).
4. Run the script, generate the PDF.
5. Schedule and conduct the review session.
6. Write `verdict.md`.
7. Archive this change; act on the verdict in `add-pairing-pipeline`.

Rollback: none needed. If the experiment goes badly (script bug, PDF misrenders), fix and re-run. The verdict isn't committed until the session completes.

## Open Questions

1. **Should the experiment include multiple retrieval variants side-by-side?** E.g., "same-theme with ≥2 mood-intersection" vs "same-theme with ≥3 mood-intersection" vs "same-theme, no mood filter, random companion." Running variants in parallel would make the MODIFY path much more informative. Lean yes; specify at implementation.

2. **Printed copy or screen review?** Printed is more immersive; screen is more flexible. Probably screen for cost, printed if the initial screen review feels rushed. Defer to operator preference.

3. **Anonymization.** Should the feedback form hide which pairing came from which retrieval variant, to reduce bias? Probably yes if variants are included. Add to implementation notes.

4. **Coupling with corpus audits.** If the review surfaces "theme X pairings all feel weak," the implication could be corpus (thin theme) or algorithm (bad retrieval) or just bad luck. Mitigation: the verdict document notes the interpretation, and `build-seed-corpus` may gain follow-up batches targeting the theme if the corpus explanation is plausible.
