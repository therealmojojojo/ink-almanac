## ADDED Requirements

### Requirement: Milestones and gating

The seed corpus SHALL pass three milestones before archive, corresponding to the two-phase build:

- **Vocabulary stable**: two consecutive canonical-list batches complete with no amendments to `mood.yaml` or `register.yaml`. (Phase 1 gate.)
- **Item pool complete**: at least **200 image items + 200 text items**, with every theme covered by at least **10 applicable items on each side** (image or text), and at least **80 anchor-eligible text items** across the pool. (Phase 1 final.)
- **Triplet pool complete**: at least **300 committed triplets** under `corpus/_triplets/`, with flavor mix approximately 60% visual-day / 40% text-day (±10 percentage points), and aligned-nocturne present on at least 40% of triplets. (Phase 2 final.)

The change SHALL NOT archive until all three milestones are reached and a final coverage audit passes.

#### Scenario: Meeting the item pool milestone

- **WHEN** a coverage audit shows 210 image items, 205 text items (including 88 anchor-eligible), and every one of the 33 themes has at least 10 items on each side applicable to it
- **THEN** the item-pool milestone is marked satisfied in the change log; Phase 2 may begin

#### Scenario: Meeting the triplet pool milestone

- **WHEN** an audit shows 312 committed triplets with 185 visual-day / 127 text-day flavors and 138 carrying `aligned_nocturne`
- **THEN** the triplet-pool milestone is marked satisfied (flavor mix ~59/41 within tolerance; nocturne coverage ~44%)

#### Scenario: Archive attempt with an unsatisfied milestone

- **WHEN** the operator attempts to archive `build-seed-corpus` and the triplet-pool audit reports 265 committed triplets
- **THEN** archival is blocked until the triplet pool reaches 300

### Requirement: Anthology-first assembly

Ingestion SHALL proceed as a sequence of canonical-list batches produced via `corpus propose-list` and executed via `corpus fetch-list`. Each batch SHALL be scoped to a single category (e.g., a poet's selected works, a photographer's canon, a named Japanese print series, an anthology section). Approved list files SHALL be committed under `openspec/changes/build-seed-corpus/lists/<category>.yaml` so the curatorial history is auditable.

Broad discovery-style ingestion (arbitrary queries without an approved list) is not part of the seed workflow.

#### Scenario: Adding a category

- **WHEN** the operator proposes and approves `lists/cavafy-essentials.yaml`, then runs `corpus fetch-list --file openspec/changes/build-seed-corpus/lists/cavafy-essentials.yaml`
- **THEN** the list file is committed to git and a new batch entry is appended to the change log referencing that list file

### Requirement: Coverage audit format

A coverage audit SHALL be a markdown document at `corpus/_audits/<iso-date>.md` containing:

- Total image count, total text count
- Per-theme table with columns: theme, image-applicable count, text-applicable count
- Per-source table showing how many items came from each source (PD connectors + web + personal-library folder)
- Rights-tier breakdown (count per tier)
- Per-category table listing each ingested canonical list with its final accepted count
- Vocabulary distribution: top 10 mood terms, top 10 register terms, and any terms used by zero items
- Flags: themes below target, unused vocabulary terms, pending-fetch items

An item counts as "applicable to theme T" when T appears in the item's `themes` field.

#### Scenario: Generating an audit

- **WHEN** the operator runs `corpus audit`
- **THEN** a new markdown file under `corpus/_audits/` is created with the current date and the sections above, and the file path is printed

### Requirement: Vocabulary stability gate

Two consecutive canonical-list batches SHALL complete with no amendments to `mood.yaml` or `register.yaml` before the "Vocabulary stable" milestone is marked satisfied. Themes and form vocabularies are fixed at `add-corpus-schema`; they do not participate in this gate.

#### Scenario: Amendment in the middle of two stable batches

- **WHEN** batch N is stable, batch N+1 proposes and ratifies an amendment to `mood.yaml`, and batch N+2 is stable
- **THEN** the stability counter resets after batch N+1; two more consecutive stable batches (N+2 and N+3) are needed before the milestone is satisfied

### Requirement: Amendments go through their own changes

Any vocabulary amendment identified during seed assembly SHALL be proposed as its own change following the `corpus-taxonomy` amendment procedure. The seed change SHALL NOT include taxonomy file diffs in its own archive.

#### Scenario: Amendment needed during list proposal

- **WHEN** `corpus propose-list` surfaces a recurring drift suggesting `mood: reverent` should be added
- **THEN** the operator aborts the proposal, opens a separate change proposal that adds the term, applies and archives it, then re-runs `propose-list` against the amended vocabulary

### Requirement: Rights-tier distribution

The seed SHALL NOT impose a ceiling on any rights tier. Given the operator's taste in 20th-century poetry and photography, the `personal_library` tier is expected to account for a substantial share of both sides. The audit SHALL record the tier breakdown so the curatorial posture is visible, but no ratio is enforced.

PD-tier items SHALL still be preferred where a canonical work exists in both tiers (for example: if a work's copyright has expired in its source jurisdiction, prefer the PD connector; do not route it through `personal_library`).

#### Scenario: PD available, personal_library proposed

- **WHEN** a list entry for Hiroshige's *The Great Wave* is proposed with `rights_tier: personal_library` and `source: web`
- **THEN** the list-proposal step warns that this work is available via `met_open_access` as `public_domain` and suggests switching the entry before fetch

### Requirement: Image resolution compliance at archive

Every image item under `corpus/images/`, `corpus/nocturne/`, and `corpus/personal_library/` SHALL meet the short-edge floor defined in `corpus-schema` (short edge ≥ 1200 px) before `build-seed-corpus` archives. The coverage audit SHALL include an "image resolution" section listing:

- Count of images at or above the short-edge floor
- Count below the floor (MUST be zero at archive)
- Count between the MUST floor and the 1800 px long-edge preference (tracked, not blocking)
- Per-id list of any non-compliant items with their actual dimensions

Items already on disk below the floor at the time this requirement takes effect SHALL be re-fetched at higher resolution via the ingestion tool's candidate rotation, or removed from the pool (there is no scanning path). The 200-image floor is measured *after* re-fetch and pruning; under-resolution items do not count.

#### Scenario: Under-resolution items block archive

- **WHEN** the audit reports 210 images, of which 7 have short-edge below 1200 px
- **THEN** the item-pool milestone is NOT satisfied, the audit names the 7 offending ids, and archive is blocked until every one is either re-fetched above the floor or removed

#### Scenario: All images comply but several below preference

- **WHEN** the audit reports zero images below the 1200 px floor, 180 above the 1800 px long-edge preference, and 30 between the floor and the preference
- **THEN** the resolution gate is satisfied; the 30 flagged items are recorded for opportunistic later upgrade but do not block archive

### Requirement: Black-and-white photography share

The seed corpus SHALL be weighted heavily toward black-and-white photography, which is the most native-fidelity medium for the 3-bit greyscale panel: 20th-century silver-gelatin work was made under exactly the tonal constraints the device reproduces.

At final audit, **at least 50% of the image pool** (combining `corpus/images/`, `corpus/nocturne/`, and the image items under `corpus/personal_library/`) SHALL have `form: photograph` and be black-and-white (not color photography). The audit SHALL record the share.

This share applies to the image pool only. The text side is unaffected.

Acceptable B&W photographic lineages include but are not limited to: French humanism (Cartier-Bresson, Doisneau, Kertész, Brassaï, Lartigue, Ronis, Izis, Boubat), American documentary and street (Evans, Lange, Frank, Arbus, Vivian Maier, Winogrand, Klein), American landscape (Weston, Strand, Ansel Adams, Minor White), Central-European (Sudek, Koudelka, Sander, Salgado), British (Brandt, Sieff), Czech surrealism (Sudek, Funke, Rössler), early photography (Atget, Abbott, Hine, Stieglitz), fashion/portrait (Avedon, Penn, Newton B&W work), Japanese postwar (Moriyama, Tōmatsu, Hosoe).

#### Scenario: B&W photography share at final audit

- **WHEN** the final audit reports 210 images total with 118 tagged `form: photograph` and `panel_fidelity: native` (B&W silver-gelatin or equivalent)
- **THEN** the share is 56.2% — above the 50% floor — and the gate is satisfied

#### Scenario: Share below floor

- **WHEN** the final audit reports 210 images with only 84 B&W photographs (40%)
- **THEN** the gate is not satisfied; archive is blocked until additional B&W-photography canonical lists are authored and fetched

### Requirement: Nocturne pool

The Night mode uses a separate image pool under `corpus/nocturne/`. Items under `corpus/nocturne/` SHALL NOT appear in `corpus/images/` and SHALL NOT participate in Gallery pairings.

The seed SHALL include at least **30** nocturne items before `build-seed-corpus` archives — enough for ~1 month of nightly rotation before repetition.

#### Scenario: Nocturne count at archive

- **WHEN** `corpus/nocturne/` holds 22 items and all other milestones are satisfied
- **THEN** archival is blocked until nocturne reaches 30

### Requirement: Language mix for text items

Text items SHALL be served in the languages established by the operator's taste file: Romanian poets in Romanian, non-Romanian poets in English translation (with original-language variants optional and welcome where the translation has a canonical English edition, e.g., Cavafy via Keeley/Sherrard, Montale, Szymborska).

At final audit, Romanian-language text items (those whose `language` array contains `ro`) SHALL account for at least **25%** of the text corpus. This ensures the Romanian voice has genuine depth and that the dashboard's bilingual character is real, not token.

#### Scenario: Romanian share at final audit

- **WHEN** the final audit shows 310 text items total with 62 containing `ro` in their language array
- **THEN** the share is 20.0% — below 25% — and archival is blocked until more Romanian text items are added

### Requirement: Change log

The change SHALL maintain an append-only log at `openspec/changes/build-seed-corpus/log.md` recording each canonical-list batch's date, category, list-file path, counts (fetched/pruned), coverage impact, and any vocabulary amendments referenced. The log is the narrative of how the corpus came to exist.

#### Scenario: Batch completion entry

- **WHEN** a `cavafy-essentials` batch of 24 list entries completes with 22 fetched, 2 pruned post-hoc
- **THEN** the log gains a dated entry naming the batch id, category, list-file path, accepted/pruned counts, coverage delta, and any referenced amendment changes
