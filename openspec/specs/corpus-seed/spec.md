# corpus-seed Specification

## Purpose
TBD - created by archiving change build-seed-corpus. Update Purpose after archive.
## Requirements
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

### Requirement: Native-B&W graphic art share

The non-photograph image corpus SHALL be restricted to **native black-and-white
graphic art** — works authored in a monochrome medium whose tonal vocabulary
maps directly onto the 3-bit greyscale panel without conversion loss.

Admissible native-B&W forms: `etching`, `engraving`, `woodblock` (monochrome
only; ukiyo-e polychrome woodblocks are excluded here and remain categorised
separately), `wood-engraving`, `lithograph` (monochrome only), `drawing`
(graphite / ink / charcoal / conté / chalk), `ink-wash`, `silverpoint`, and
`aquatint`. `poster` items qualify only when the source is a monochrome
lithographic poster.

Inadmissible: any item with `form: painting` whose source was polychrome and
has been desaturated to greyscale. The 2026-04-19 review found such items
produce unacceptable quality on the 3-bit panel — tonal range collapses,
chroma-dependent structure disappears, and the image reads as muddy rather
than graphic. These items SHALL be refused at ingestion and removed when
encountered during audit.

The `corpus audit` report SHALL surface a "native-B&W graphic art" section
counting non-photograph images by form and flagging any `form: painting`
items that are not specifically catalogued under the aligned-nocturne
exception (see `Nocturne pool` — which may include paintings authored as
true tonal-monochrome works, e.g., grisaille, but SHALL NOT include
desaturated polychrome paintings).

#### Scenario: Desaturated painting refused at ingestion

- **WHEN** a staged sidecar declares `form: painting` with a source image
  that is a greyscale conversion of a polychrome oil painting
- **THEN** commit refuses the item with `form 'painting' is not a native-B&W
  graphic-art form; desaturated polychrome paintings are not admissible for
  the gallery image pool`

#### Scenario: Monochrome lithograph accepted

- **WHEN** a staged sidecar declares `form: lithograph` with a monochrome
  source (black on cream paper, e.g., a Daumier *Charivari* plate scanned
  from the original sheet)
- **THEN** commit accepts the item subject to the other ingestion gates

#### Scenario: Grisaille painting under nocturne exception

- **WHEN** a nocturne-pool sidecar declares `form: painting` for a work
  authored as a true tonal monochrome (e.g., grisaille, or a B&W-only
  medium)
- **THEN** the item is admissible only in the nocturne pool and the audit
  flags it as a named exception with its monochrome-authorship citation

### Requirement: Graphic-arts canon coverage

The seed SHALL maintain a non-photograph image spine anchored by canonical
graphic-arts creators enumerated in
`openspec/changes/add-bw-graphic-arts-canon/lists/top-bw-graphic-arts.yaml`
(28 creators spanning old-master printmaking, 19th-century print, fin-de-
siècle, German Expressionism, American 20th-century graphic work, modernist
drawing, Japanese ink tradition, contemporary drawing, and pen-and-ink
illustration).

At final audit after this change archives, the non-photograph image pool
SHALL include at least 5 canonical works from each `canon_weight: core`
creator and at least 3 from each `canonical` creator. The audit SHALL list
any creator below floor with the count short.

#### Scenario: Core-creator floor

- **WHEN** the final audit reports 4 canonical Dürer items committed
- **THEN** the graphic-arts coverage gate is not satisfied until Dürer
  reaches 5 canonical items

### Requirement: Pen-first non-photograph spine

The non-photograph image pool SHALL be weighted toward native line
work, because the 3-bit greyscale panel reproduces line-on-white and
flat areas faithfully but collapses tonal mid-greys.

At final audit after this change archives, at least **60% of the
non-photograph image pool** SHALL have `form` in one of:

- `drawing` (pen, ink, charcoal, brush — excluding soft-graphite /
  conté tonal drawings)
- `woodblock` or `wood-engraving` (monochrome only)
- `ink-wash` (sumi-e, Zen brushwork)
- `poster` (flat-shape poster work — Sachplakat, Art Deco posters)

The remaining 40% MAY be tonal-print (etching, aquatint, crayon-
lithograph, tonal-drypoint); no hard ceiling, but individual creators
working primarily in tonal-print SHALL be capped at **no more than
3 items** in the gallery image pool. Excess tonal-print items remain
admissible on disk with `panel_verdict: flag` and are excluded from
triplet selection until they pass a panel-rendered review.

The audit SHALL list: total non-photograph images; count in each
`form`; share of pen-first forms as a percentage; per-creator counts
for tonal-print creators flagging any above the 3-item cap.

#### Scenario: Pen-first share at final audit

- **WHEN** the final audit reports 180 non-photograph images total,
  with 118 tagged `form: drawing`, `form: woodblock`, `form:
  wood-engraving`, `form: ink-wash`, or `form: poster`
- **THEN** the share is 65.5% — above the 60% floor — and the gate is
  satisfied

#### Scenario: Tonal-print creator above the cap

- **WHEN** Rembrandt holds 7 etching items in `corpus/images/`
- **THEN** the audit flags the creator as above the 3-item tonal-print
  cap and lists the 4 items that MUST be either re-classified as
  `panel_verdict: flag` or removed

### Requirement: Contemporary pen-and-ink canon coverage

The seed SHALL include a contemporary pen-and-ink / manga / ligne-
claire / caricature spine anchored by the 20 creators enumerated in
`openspec/changes/add-contemporary-pen-canon/lists/top-contemporary-
pen.yaml`, with coverage organised into four streams: manga (≥ 7),
Western comic-strip / cartoon (≥ 6), XKCD (≥ 12 strips), and
caricature + contemporary ink (≥ 6).

At archive, each `canon_weight: core` creator SHALL have ≥ 5 items,
each `canonical` SHALL have ≥ 3, allowing for one below-floor
creator per stream if web fetch demonstrably cannot retrieve more
at quality.

#### Scenario: Contemporary canon floor

- **WHEN** the final audit reports Tezuka 6, Toriyama 4, Miyazaki 4,
  Taniguchi 3, Matsumoto 3, Urasawa 4, Fujio 3 — and every other
  stream also at floor
- **THEN** the contemporary-canon gate is satisfied

