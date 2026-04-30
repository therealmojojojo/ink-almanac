## ADDED Requirements

> Architecture note: see `design.md` in this change folder for the harvest-and-prune primary flow. The requirements below describe both paths. The `propose-list` / `fetch-list` requirements describe the targeted per-work (secondary) path; the harvest, reconciliation, and vision-tagging requirements describe the primary photographer-level flow.

### Requirement: Photographer harvest

The CLI SHALL expose `corpus harvest-photographer <creator-id>` that, given an entry from the Stage-1 shortlist, performs a photographer-level image harvest via the web-search channel and produces a contact sheet for operator review.

The harvest SHALL:

- Construct a DDG query of the form `"<Creator> best photos"`.
- Apply DDG filters `size:Large, type:photo, color:Monochrome` without a `layout:` filter (orientation diversity is intentional at this stage).
- Fetch up to 40 candidates via the DDG `vqd` → `i.js` two-step handshake.
- Apply the candidate gate: surname present in title / url / image-url (word-boundary), resolution ≥ orientation-aware MUST floor per `corpus-schema`, host not in the configured reject-list.
- Deduplicate via perceptual hash (dHash-8, Hamming ≤ 8); keep the highest-resolution representative of each cluster.
- Produce a contact sheet at `corpus/_staging/harvest-<creator-id>/contact-sheet.{html,md}` with thumbnails, source domains, dimensions, and DDG rank.

#### Scenario: Harvesting a creator

- **WHEN** the operator runs `corpus harvest-photographer fan-ho` against an approved Stage-1 entry
- **THEN** the tool fetches candidates from DDG, gates them to ~15–25 usable items, renders a contact sheet, and exits zero without committing sidecars until the operator accepts via the contact sheet

#### Scenario: Candidate rejected by gate

- **WHEN** a candidate is above the MUST floor but its host is `pinterest.com`
- **THEN** the candidate does not appear in the contact sheet; the batch report logs one `rejected: banned_domain` entry

#### Scenario: Deduplication across sources

- **WHEN** two candidates from different domains have pHash Hamming distance ≤ 8
- **THEN** the contact sheet shows one representative (the higher-resolution) with a note indicating the alternate source; the other is not presented independently

### Requirement: Claude-vision tagging at commit time

For every item committed through `harvest-photographer` or `fetch-work`, the CLI SHALL invoke a Claude-vision call at commit time that, given the candidate thumbnail plus the known creator, proposes `title`, `year`, `themes[]`, `mood[]`, `register[]`, `form`, and `panel_fidelity`. The proposal SHALL be validated against the ratified taxonomy before the sidecar is written.

Claude SHALL reply with a structured rejection when the image is: a portrait of the creator, a book cover, an exhibition poster, or evidently not a work by that creator. Rejected items SHALL NOT be committed; they are recorded in the batch report and presented for operator resolution.

This Requirement supersedes "Claude-assisted tagging at list-proposal time" for the harvest and fetch-work paths. The list-proposal-time tagging requirement remains in force only for operator-hand-authored `propose-checklist` output consumed by the targeted path.

#### Scenario: Vision accepts and tags a harvest item

- **WHEN** the operator accepts a contact-sheet entry whose thumbnail shows the Migrant Mother photograph
- **THEN** the commit step calls Claude-vision, receives `{title: "Migrant Mother", year: 1936, themes: [portrait-and-face, tender-companionship, rural-pastoral, mortality], mood: [grave, tender, stoic], register: [iconic, documentary], form: photograph, panel_fidelity: native}`, validates every tag against the taxonomy, writes the sidecar, fetches the full binary, and updates `_manifest.json`

#### Scenario: Vision rejects a candidate as a portrait

- **WHEN** a harvested candidate is actually a portrait of the creator (rather than their work)
- **THEN** Claude-vision returns a rejection; the commit step does not write a sidecar, and the batch report records `rejected: vision_portrait_of_creator`

### Requirement: Stage-2 reconciliation

The CLI SHALL expose `corpus reconcile-checklist --creator <id>` that matches committed sidecars for that creator against the Stage-2 YAML checklist file and updates each checklist entry's `status` field.

A match is recorded when the creator matches AND either:

- fuzzy title-match (token-set ratio ≥ 0.75) between the committed sidecar's `title` and the checklist entry's `title`, OR
- Claude-vision cross-check confirms the committed thumbnail plausibly depicts the work described in the checklist entry.

Matched entries receive `status: checked`, `committed_id: <sidecar-id>`, and `checked_by: harvest | targeted-fetch | operator-manual`.

`corpus reconcile-checklist --all` produces an aggregate coverage dashboard across every Stage-2 file in the corpus.

#### Scenario: Harvest covers most of a checklist

- **WHEN** `harvest-photographer dorothea-lange` commits 14 items and the Stage-2 checklist for Lange has 18 entries
- **THEN** `reconcile-checklist --creator dorothea-lange` reports (for example) 12 of 18 entries checked, 6 unchecked; the 12 checklist entries have `status: checked` and `checked_by: harvest`

#### Scenario: Aggregate coverage

- **WHEN** `reconcile-checklist --all` is run after 30 creator harvests
- **THEN** the report prints per-creator coverage percentages and an aggregate (for example: 485 of 675 checklist entries checked, 72%)

### Requirement: Query-expansion ladder for unchecked items

For each checklist entry whose `status` is still `pending` after harvest, the CLI SHALL expose `corpus fetch-work --escalate` that applies up to eight query variants in a documented order:

1. `"<Creator> — <title>"` (em-dash, baseline)
2. `"<Creator> — <title> <year>"`
3. `"<Creator> — <title> <series-or-context>"` (e.g., "Decisive Moment")
4. Title translated (English ↔ native language)
5. Baseline + `layout:<Tall|Wide|Square>` from the checklist's `orientation` field
6. Site-restricted museum-scoped query (e.g., `site:moma.org <creator> <title>`)
7. `"<Creator> iconic photographs"` / `"<Creator> masterpieces"` / `"<Creator> retrospective"`
8. Subject-keyword-only lexical fallback (e.g., `"HCB puddle leap 1932"`)

Each variant runs against the same candidate gate (surname, resolution, not-banned). The first variant whose top-ranked candidate passes is committed. When all variants are exhausted without a pass, the checklist entry receives `status: targeted-fetch-failed`, and the operator's drop-or-substitute decision queue gains the entry. There is no queue-for-scan path (per the ratified no-scanning policy in `corpus-schema`).

The ladder SHALL instrument per-variant outcomes so the ordering can be tuned from real data.

#### Scenario: Escalation succeeds on variant 2

- **WHEN** `fetch-work --escalate --id hcb-behind-gare-saint-lazare` is run and variant 1 returns no passing candidate but variant 2 (with `1932` appended) does
- **THEN** the variant 2 result is committed; the batch report records `escalation_success: variant_2 (+year)`

#### Scenario: Escalation exhausts all variants

- **WHEN** none of the eight variants produces a passing candidate for `izis-montreur-ours`
- **THEN** the checklist entry is marked `status: targeted-fetch-failed`; no sidecar is written; the operator is presented with drop-or-substitute options

### Requirement: Shortlist and checklist proposal

The CLI SHALL expose two proposal subcommands:

- `corpus propose-shortlist --category <name>` — Claude drafts the Stage-1 artifact: a ranked list of creators (photographers, poets, print series) for a named category, with `id`, `name`, `years`, `lineage`, `canon_weight`, and dedup annotations against the existing corpus. This shortlist is the input to `harvest-photographer`.
- `corpus propose-checklist --creator <id>` — Claude drafts the Stage-2 artifact: a per-creator works checklist with `title`, `year`, `orientation`, `distinctive` terms, taxonomy-compliant tags, and `status: pending` for each entry. Output lives under `corpus/_staging/works-<creator>.yaml` and serves as the curatorial checklist against which harvest results are reconciled (see "Stage-2 reconciliation").

Both commands prompt-cache the full taxonomy and halt on vocabulary drift with the map / drop / amend flow.

Neither command is a precondition for fetch: the harvest flow operates from the Stage-1 shortlist alone. Stage-2 checklists are consumed by `reconcile-checklist` and `fetch-work --escalate` (targeted path) when harvest coverage is incomplete.

#### Scenario: Proposing a shortlist

- **WHEN** the operator runs `corpus propose-shortlist --category bw-photography --out shortlists/bw.yaml`
- **THEN** `shortlists/bw.yaml` is written with ~50 creators ranked by canonical weight, each carrying a stable id, years, lineage tag, and existing-corpus dedup count

#### Scenario: Proposing a per-creator checklist

- **WHEN** the operator runs `corpus propose-checklist --creator henri-cartier-bresson --out corpus/_staging/works-henri-cartier-bresson.yaml`
- **THEN** the file is written with ~15–25 entries, each with title, year, orientation, distinctive terms, tags drawn only from the ratified taxonomy, and `status: pending`

#### Scenario: Legacy Canonical-list proposal

The CLI SHALL retain `corpus propose-list --category <name> [--out <path>]` as an alias for `propose-checklist --creator <name>`, producing checklist-shaped output. This accommodates existing workflow scripts referring to `propose-list`.

### Requirement: Canonical-list proposal (legacy, for targeted-fetch path)

The CLI SHALL expose `corpus propose-list --category <name> [--out <path>]` that invokes Claude to produce a YAML list file proposing a canonical set of works for a named category (a poet, a photographer, a named series, an anthology section).

The prompt SHALL include:

- The category name.
- The ratified `corpus/_taxonomy/*.yaml` files, with an instruction that every proposed tag MUST be drawn from them.
- Per-item output schema: stable kebab-case `id`, `title`, creator, proposed `rights_tier`, proposed `themes`, `mood`, `register`, `form`, a `source` connector name or `web`, and for web items a small set of reputable candidate URLs the fetcher can try.

The list file SHALL be a YAML document with a top-level `category` field and an `items` array. The operator reviews the file before running `corpus fetch-list` against it.

Prompt caching SHALL be used for the vocabulary block so repeated `propose-list` calls within a session are cheap.

#### Scenario: Proposing a canon

- **WHEN** the operator runs `corpus propose-list --category cartier-bresson-canon --out lists/hcb.yaml`
- **THEN** `lists/hcb.yaml` is written with ~20–40 items, each carrying a stable id, title, proposed tags drawn only from the ratified taxonomy, and at least one candidate source URL, and the tool exits zero

#### Scenario: List proposal drifts from taxonomy

- **WHEN** Claude proposes a `mood: reverent` tag for an item and `reverent` is not present in `corpus/_taxonomy/mood.yaml`
- **THEN** `propose-list` halts before writing the file, reports the drift event, and prompts the operator to (a) map the term to an existing one, (b) drop the tag for that item, or (c) abort and propose a taxonomy amendment via a separate change

### Requirement: Acquisition channels

The CLI SHALL expose `corpus fetch-list --file <path>` that executes an approved list file. `fetch-list` SHALL support two acquisition channels:

**PD connectors** — for items whose `rights_tier` is `public_domain` or `cc0`:

- `met_open_access`, `rijksmuseum`, `gallica_bnf`, `loc_pnp`, `project_gutenberg`, `wikisource` (with language-code selection), `wikimedia_commons`

Each connector SHALL accept a query of the form `(title, creator, optional source-native id)` and return the best-matching record with a full-binary URL suitable for download and a canonical `source_url`.

**Web-search channel** — for items whose `rights_tier` is `personal_library`:

The channel SHALL accept a list item's title + creator (and optional candidate URLs from `propose-list`), perform web search, prefer reputable domains (museum sites, artist estates, reputable literary archives, publisher previews, Wikipedia/Wikimedia as fallback), download the best-resolution reproduction available for images, and extract verbatim text for text items. Retrieved text SHALL be written to `<id>.body.<lang>.txt` files per `corpus-schema`. Retrieved images SHALL be stored under `corpus/personal_library/` as binaries.

#### Scenario: PD connector fetches a listed work

- **WHEN** `fetch-list` encounters an item `{ id: "hokusai-great-wave", source: "met_open_access", rights_tier: "public_domain", ... }` with a known Met object id
- **THEN** the tool retrieves the full-resolution image from the Met Open Access API, writes the sidecar under `corpus/images/`, places the binary beside it, and records the manifest entry

#### Scenario: Web-fetch for a personal-library image

- **WHEN** `fetch-list` encounters a `rights_tier: personal_library, source: web` image entry
- **THEN** the channel performs web search, ranks candidates preferring reputable domains AND higher resolution, downloads the highest-resolution image that meets the `corpus-schema` resolution floor (rotating to the next candidate if a download falls below it), writes the sidecar under `corpus/personal_library/`, places the binary beside it, records `source_url` as the URL actually used, and populates `pixel_width` / `pixel_height`. If no candidate meets the floor, the item is marked `fetch-failed: resolution below floor` and left for retry.

#### Scenario: Web-fetch yields no satisfactory source

- **WHEN** web search for an item returns no reputable candidates above a configurable quality threshold
- **THEN** the tool skips the item, logs it in the batch report as `fetch-failed: no reputable source`, and continues with remaining items

### Requirement: Claude-assisted tagging at list-proposal time

Claude-assisted tagging SHALL happen during `corpus propose-list`, not during `fetch-list`. List entries arrive with `themes`, `mood`, `register`, and `form` already populated. `fetch-list` SHALL write sidecars from the list entries without re-invoking Claude, except to fill any list entry whose tag fields are absent (in which case it halts with an error asking the operator to re-propose or complete the list).

#### Scenario: List with missing tags

- **WHEN** `fetch-list` encounters a list entry lacking `themes`
- **THEN** the tool halts with `list entry <id> missing required tag fields`, writes no sidecar for that item, and exits non-zero

### Requirement: Contact sheet and batch pruning

After `fetch-list` completes, the tool SHALL produce a contact sheet at `corpus/_staging/<batch-id>/contact-sheet.html` (and a sibling `.md`) containing:

- A thumbnail grid of all fetched images with ids and titles underneath
- A scrollable list of all fetched text items with body excerpts and ids

The operator SHALL prune unwanted items via `corpus prune --batch <id> --ban <id1> <id2> ...`. Pruning SHALL delete the sidecar, any body files, any binaries, and the manifest entries for each banned id, and append a pruning record to the batch report.

#### Scenario: Contact sheet produced after fetch

- **WHEN** a `fetch-list` run successfully writes 32 items and fails on 3
- **THEN** `corpus/_staging/<batch-id>/contact-sheet.html` lists 32 items with thumbnails/excerpts, and the batch report lists the 3 failures separately

#### Scenario: Pruning removes a banned item completely

- **WHEN** the operator runs `corpus prune --batch b-2026-05-01 --ban example-banned-id`
- **THEN** the sidecar, the binary, and the `_manifest.json` entry for `example-banned-id` are removed, and a line is appended to the batch report recording the ban

### Requirement: Binary and body-file fetch retry

A `corpus fetch-binaries --batch <id>` subcommand SHALL re-run binary and body-file fetch for items whose initial fetch failed, without re-proposing the list.

#### Scenario: Retry after fetch failure

- **WHEN** `fetch-list` produced 3 items in pending-fetch state and `corpus fetch-binaries --batch <id>` is run
- **THEN** the tool retries fetch for exactly those 3 items, rotates candidate URLs where applicable, and updates the batch report with new outcomes

### Requirement: Batch report

At batch completion, `fetch-list` SHALL produce a report at `corpus/_staging/<batch-id>/report.md` containing:

- Batch id, source list file, and channels used
- Count of list entries processed, fetched successfully, failed, and pruned post-hoc
- Tag-distribution histogram across fetched items
- Theme-coverage delta (before vs after, per theme, counting both sides)
- List of fetch failures with reasons
- List of banned/pruned items with reasons
- Claude call count and approximate cost

#### Scenario: Report after a mixed-result batch

- **WHEN** a list of 40 items completes with 37 fetched, 3 fetch-failed, and 2 pruned post-hoc
- **THEN** the report file contains those counts, the tag histogram, the coverage delta, the fetch-failure reasons, and the pruned ids with reasons

### Requirement: Claude-tagging in ingest-personal

The `corpus ingest-personal` subcommand SHALL accept an opt-in `--claude-tag` flag that, at stage time, populates `themes` / `mood` / `register` / `form` per file: images via a preview call, texts via the full content. Tags produced this way SHALL still validate against the ratified taxonomy at commit time — no drift reaches committed sidecars.

#### Scenario: Folder ingest with Claude-tag

- **WHEN** the operator runs `corpus ingest-personal --folder ~/Downloads/batch --citation "..." --claude-tag`
- **THEN** each staged sidecar is written with tag fields populated from the Claude call, operator review is optional rather than required, and commit validates tags against the taxonomy before moving files

### Requirement: Upload-to-backup at fetch time

On successful fetch by `fetch-list`, the tool SHALL upload the new content body to the configured backup location (the scheme declared in `backup_uri`). Supported schemes: `file://`, `icloud://`, `b2://`, `s3://`. Personal-library tier content SHALL continue to route only to operator-controlled schemes (`file://`, `icloud://`) unless the operator has explicitly opted in to `b2://` / `s3://` for that tier.

#### Scenario: Upload to B2 at fetch time

- **WHEN** the operator has configured `CORPUS_BACKUP_SCHEME=b2://inkplate-corpus/` for PD content and `fetch-list` succeeds for a PD Hokusai binary
- **THEN** after the local write, the binary is uploaded to `b2://inkplate-corpus/corpus/images/<id>.jpg`, the manifest entry's `backup_uri` reflects that location, and `corpus restore` in a scratch clone can subsequently rebuild the file from B2

### Requirement: Triplet proposal workflow

The CLI SHALL expose three triplet-automation subcommands:

- `corpus propose-triplets [--count N] [--seed-themes ...] [--out <path>]` — Claude proposes N triplets drawing from the current item pool; output is a YAML batch file with per-triplet fields `id`, `anchor`, `summary`, `gallery`, `flavor`, optional `aligned_nocturne`, `themes`, and a one-sentence `note`.
- `corpus review-triplets --file <path>` — operator-facing contact sheet at `corpus/_staging/<batch-id>/triplets-review.{html,md}` rendering each triplet for accept / reject / edit.
- `corpus commit-triplets --file <path>` — validates accepted triplets against `corpus-triplets`, auto-fetches any anchor named by citation that isn't yet in the pool (via the web-search channel), writes valid triplets to `corpus/_triplets/`, leaves rejected / edited-but-unaccepted triplets in the batch file.

#### Scenario: Proposing and committing a triplet batch

- **WHEN** the operator runs `corpus propose-triplets --count 20 --seed-themes morning still-life`, reviews and accepts 18, then runs `corpus commit-triplets`
- **THEN** 18 new files appear under `corpus/_triplets/` with the correct ids, auto-fetched anchors (if any) are ingested under `corpus/personal_library/`, and the tool exits zero

#### Scenario: Commit auto-fetches a new anchor

- **WHEN** an accepted triplet references an anchor by citation that is not in the item pool
- **THEN** the commit step fetches the anchor via the web-search channel, writes a `rights_tier: personal_library` sidecar with the supplied citation, updates the manifest, and then writes the triplet file — all in one commit

### Requirement: Pydantic model layer

Sidecars, taxonomy files, manifest entries, backup URIs, and canonical-list files SHALL be represented by `pydantic` models shared across all ingestion subcommands. `corpus validate` SHALL use those models (replacing the current dict-based validation) so the same parse rules apply at write time, read time, and commit time.

#### Scenario: Model-driven validation

- **WHEN** `corpus validate` parses a sidecar whose `year` is a string instead of int-or-ISO-date
- **THEN** the pydantic model rejects the parse and the validator reports the specific field + expected type, identical to what ingestion subcommands would report at write time
