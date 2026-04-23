## ADDED Requirements

### Requirement: Pairing generation against v1 corpus

The experiment SHALL generate exactly 30 days of pairings using the ratified retrieval algorithm:

1. For each day, select a theme from the ratified 33-theme set (following a monthly shuffle for variety).
2. Build tag queries (theme filter, exclusion of items "used" in earlier experiment days).
3. Within the shortlist, random-pick a hero (image or text, according to a deliberate flavor assignment — visual-day or text-day).
4. Mood/register intersection with the hero produces a companion shortlist on the other side; random-pick a companion.

The experiment SHALL use the actual `corpus/` state at execution time. Exclusion SHALL apply within the 30-day experiment horizon; the past-year exclusion is not applicable here because the experiment is a single 30-day run.

#### Scenario: 30-day run produces 30 unique pairings

- **WHEN** the pairing script is executed once
- **THEN** 30 pairings are produced, each with a unique hero and a distinct companion, with no item appearing as hero twice in the 30 days

### Requirement: Review document

The experiment SHALL render a single PDF document presenting all 30 days for review, in the following structure:

- Cover page: date range, corpus snapshot (item counts per theme), methodology summary
- 30 pairing pages: each page shows the Gallery face for that day on the left and the Summary face on the right, at reduced size suitable for a printed page (or on-screen review)
- Feedback form at the back: a per-day checklist (works / doesn't / unclear) plus a free-form notes area
- Summary statistics: themes used, forms used, rights-tier distribution, a few representative pairings highlighted

The PDF is regenerated on each run and is NOT committed to the repository. The generation script IS committed.

#### Scenario: Generating the review PDF

- **WHEN** the operator runs the experiment script
- **THEN** a PDF is written to `openspec/changes/experiment-pairing-viability/review.pdf` containing the cover, 30 pairing pages, and the feedback form

### Requirement: Review session

A review session SHALL include, at minimum, the operator. The wife's participation is strongly preferred since the "wife factor" is the project's stated quality bar. The session SHALL:

- Walk through the 30 days in calendar order
- Record per-day working / not-working / unclear verdicts in the feedback form
- Capture free-form observations about what categories of pairings land vs. fail
- Identify patterns: e.g., "text-day pairings feel stronger than visual-day", or "romanian-voice theme pairings consistently work"

#### Scenario: Completed review with clear signal

- **WHEN** the review session completes and 24 of 30 days are marked working
- **THEN** the verdict candidate is **GO**

#### Scenario: Completed review with mixed signal

- **WHEN** the review session completes and 14 of 30 days are marked working, 10 unclear, 6 not working, with patterns suggesting visual-day is weak
- **THEN** the verdict candidate is **MODIFY** with the specific modification noted (e.g., "text-day only" or "visual-day requires tighter hero/companion mood-axis alignment")

### Requirement: Verdict document

The verdict SHALL be recorded at `openspec/changes/experiment-pairing-viability/verdict.md` with the following structure:

- **Verdict**: one of `GO`, `MODIFY`, `DROP`
- **Rationale**: 2–5 sentences summarizing why
- **Evidence**: review-session summary statistics (counts, noted patterns)
- **Implications for `add-pairing-pipeline`**: any concrete design changes that must flow into that change's specs before implementation
- **Date of verdict**
- **Participants**

This document IS committed. Subsequent changes reference it.

#### Scenario: GO verdict committed

- **WHEN** the review supports GO and the verdict document is written
- **THEN** `add-pairing-pipeline` may proceed to `/opsx:apply` with the existing specs; no spec modifications are required

#### Scenario: MODIFY verdict with specific changes

- **WHEN** the verdict is MODIFY with "text-day only, drop visual-day" as the required change
- **THEN** `add-pairing-pipeline`'s specs are amended (via an updating change or a spec edit within that proposal before it applies) to reflect text-day-only retrieval, and this change's archival notes the modification

#### Scenario: DROP verdict

- **WHEN** the verdict is DROP
- **THEN** `add-pairing-pipeline` is withdrawn (removed from the plan or converted into a much smaller theme-only rotation change), and Gallery + Summary delight zones are redesigned to rotate independently

### Requirement: Honest conclusion

The verdict SHALL be recorded honestly even if the outcome is DROP. The experiment exists specifically so that a negative result is allowed without loss of face, and so the project's architecture reflects actual quality rather than committed intent.

#### Scenario: Negative but clean outcome

- **WHEN** the review shows weak pairing across the board, and MODIFY tweaks tried over a second 30-day run still don't produce a satisfying result
- **THEN** DROP is recorded with full rationale; `add-pairing-pipeline` is withdrawn without prejudice to the rest of the project
