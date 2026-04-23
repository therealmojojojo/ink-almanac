## ADDED Requirements

### Requirement: CLI surface

The ingestion tooling SHALL expose a single CLI entry point `corpus` with the following subcommands:

- `corpus validate [--full]` — validates sidecars, triplets, and manifest entries against `corpus-schema`, `corpus-taxonomy`, and `corpus-triplets`. `--full` additionally verifies sha256 of every manifest entry.
- `corpus audit [--out <path>] [--format md|json]` — read-only coverage and gate-status report (folder × tier, theme coverage per side, panel-fidelity distribution, panel-verdict distribution, resolution status, gate tracking against the ratified corpus-seed floors).
- `corpus refetch [ids...] [--dry]` — rotates image items whose `panel_verdict` is `reject` through a fixed set of free sources (Wikimedia Commons, ARTIC, Met Open Access) at the `corpus-schema` resolution floor.
- `corpus ingest-personal --folder <path> --citation "<string>" [--nocturne] [--language <codes>] [--source-url <url>] [--backup-scheme file|icloud]` — stages a folder of web-downloaded images or typed text fragments into `corpus/_staging/<batch-id>/`.
- `corpus ingest-personal --commit --batch-id <id> [--dry-run]` — validates a staged batch and moves it into `corpus/personal_library/` (or `.../nocturne/` with `--nocturne`), appending manifest entries.
- `corpus restore [--check] [--verify] [--force] [paths...]` — rebuilds missing binaries / body files from manifest `backup_uri` entries; verifies sha256 on every restored file.
- `corpus help` — prints the subcommand reference.

#### Scenario: Running the top-level CLI with no subcommand

- **WHEN** the operator runs `corpus` without arguments
- **THEN** the CLI prints a usage summary listing all implemented subcommands with their one-line descriptions, and exits zero

### Requirement: Validation at the boundary

Every sidecar, body file, and manifest entry SHALL pass `corpus-schema` and `corpus-taxonomy` validation before being written by any subcommand that writes. Validation failures SHALL halt the write and report the exact rule breached with the offending value.

`corpus validate` SHALL additionally be runnable standalone to validate the entire `corpus/` directory, producing a report of all violations and exiting non-zero iff any errors are present.

#### Scenario: Attempt to commit a staged sidecar missing required field

- **WHEN** `corpus ingest-personal --commit` encounters a staged sidecar that lacks `rights_tier`
- **THEN** the commit is aborted, every violation across the batch is reported (e.g., `<path>: missing required field `rights_tier``), and no files are moved out of staging

#### Scenario: Full-corpus validation

- **WHEN** the operator runs `corpus validate`
- **THEN** the tool scans every sidecar, every triplet, every binary vs manifest entry under `corpus/`, prints a report with zero or more violation lines, and exits zero iff every check passes

#### Scenario: Full-manifest sha256 verification

- **WHEN** the operator runs `corpus validate --full`
- **THEN** the tool recomputes sha256 of every manifest-referenced file and reports `sha256 mismatch: expected <a>, got <b>` for any divergence

### Requirement: Personal-library folder-mode ingestion

The `corpus ingest-personal` subcommand SHALL support a two-phase workflow for ingesting a folder of web-downloaded images or typed text fragments:

1. **Stage.** The tool enumerates supported files in the source folder, copies them under `corpus/_staging/<batch-id>/binaries/`, and writes a skeleton sidecar per file under `corpus/_staging/<batch-id>/sidecars/` containing every mandatory `corpus-schema` field. For image files, Pillow is used to record actual `pixel_width` / `pixel_height` at stage time. Tag fields (`themes`, `mood`, `register`, `form`) MAY be pre-populated by the agent authoring the batch; in the absence of agent-authored tags they are seeded as placeholders that `commit` will reject.

2. **Commit.** The tool validates every staged sidecar against `corpus-schema` and `corpus-taxonomy`, enforces the orientation-aware resolution floor (`corpus-schema`'s "Image resolution floor" requirement), refuses `panel_fidelity: color-dependent`, refuses to overwrite existing item ids, and writes manifest entries with tier-appropriate `backup_uri` (`file://` default; `icloud://` via `--backup-scheme icloud`; `b2://` / `s3://` refused for the personal-library tier). On success, the staging directory is removed.

The agent (Claude) is expected to author the complete sidecar at stage time — including tags — in the dominant single-item workflow driven by operator-supplied URLs. The hand-edit-after-stage path exists as a fallback.

#### Scenario: Ingesting a folder of web-downloaded images

- **WHEN** the operator runs `corpus ingest-personal --folder ~/Downloads/iancu-dada --citation "Iancu, *Dada Portraits*, Editura Vellant, 2016"` against a folder where each file's tags have already been authored
- **THEN** staged sidecars land under `corpus/_staging/<batch-id>/` carrying the shared citation and the authored tags; `corpus ingest-personal --commit --batch-id <id>` validates the batch and moves sidecars + binaries into `corpus/personal_library/` with matching manifest entries

#### Scenario: Commit halts on color-dependent panel_fidelity

- **WHEN** a staged sidecar declares `panel_fidelity: color-dependent`
- **THEN** commit refuses the item with an explicit error and no files move out of staging

### Requirement: Direct sidecar authoring (single-item path)

The agent-driven, single-item acquisition path SHALL be supported by the same tooling boundary contracts as folder-mode: every sidecar and manifest entry written to `corpus/` — whether written programmatically via `ingest-personal` or placed directly by an editor — SHALL validate clean under `corpus validate`. No ingestion path bypasses `corpus-schema` or `corpus-taxonomy`.

#### Scenario: Ingestion via direct sidecar authoring

- **WHEN** the operator supplies a URL identifying a named work, and the agent authors the sidecar + copies the binary + appends the manifest entry directly (without going through `corpus/_staging/`)
- **THEN** the resulting sidecar and manifest entry pass `corpus validate` identically to items that went through `ingest-personal --commit`

### Requirement: Backup URI format

The `backup_uri` field in `_manifest.json` entries SHALL be a string in one of the following forms:

- `file://<absolute-path>` — local filesystem backup (default, including the seed-corpus baseline where `backup_uri` points at the corpus path itself)
- `icloud://<relative-path>` — iCloud Drive path, resolved against `INKPLATE_ICLOUD_ROOT`
- `b2://<bucket>/<key>` — Backblaze B2
- `s3://<bucket>/<key>` — Amazon S3 or S3-compatible storage

Personal-library content (binaries or body files) SHALL route only to operator-controlled schemes (`file://`, `icloud://`) unless the operator explicitly opts in. `b2://` and `s3://` SHALL be refused for `rights_tier: personal_library` items at both write time (ingest-personal) and restore time.

#### Scenario: Personal-library backup refused for b2

- **WHEN** `corpus ingest-personal --commit --backup-scheme b2` is attempted for a personal-library batch
- **THEN** commit refuses with "personal-library permits only operator-controlled schemes (file, icloud)" and no files move

### Requirement: Restore from manifest

The `corpus restore` subcommand SHALL read `_manifest.json`, identify content bodies missing from disk (or optionally re-verify all), and re-fetch each from its `backup_uri`. After fetch, sha256 SHALL be recomputed and compared against the manifest entry; mismatches SHALL halt the per-item restore, leave the file absent, and report the discrepancy.

Supported schemes: `file://` (local filesystem copy), `icloud://` (resolved against `INKPLATE_ICLOUD_ROOT`), `b2://` and `s3://` reserved for future implementation — current builds report a diagnostic and skip those entries.

#### Scenario: Restoring a missing file-scheme binary

- **WHEN** a binary listed in `_manifest.json` with `backup_uri: file:///Volumes/Backup/inkplate/corpus/images/durer-melencolia-i.jpg` is absent from disk, the backup location has the file, and `corpus restore` is run
- **THEN** the binary is copied to its corpus path, sha256 is verified against the manifest entry, and the tool exits zero

#### Scenario: Tampered content in backup

- **WHEN** a backup content body has been modified and its sha256 no longer matches the manifest
- **THEN** `corpus restore` halts at the affected item, leaves the file absent locally, and reports `sha256 mismatch (manifest <a>, disk <b>)`

#### Scenario: Check-only mode

- **WHEN** the operator runs `corpus restore --check`
- **THEN** the tool reports which content bodies are missing and from which `backup_uri` they would be fetched, writes nothing, and exits zero iff nothing is missing

### Requirement: Rights-tier routing

Every ingestion subcommand and every restore operation SHALL enforce the rights-tier obligations defined in `corpus-schema` "Rights tiers and their obligations":

- Items with `rights_tier: personal_library` SHALL be placed under `corpus/personal_library/` (or `corpus/personal_library/nocturne/`) and nowhere else.
- Items with `rights_tier: public_domain` or `cc0` SHALL be placed under `corpus/images/`, `corpus/texts/`, or `corpus/nocturne/` and not under `corpus/personal_library/`.
- Personal-library binaries SHALL be git-ignored via the root `.gitignore` rules.
- Personal-library backup routing SHALL be constrained to operator-controlled schemes as defined in "Backup URI format" above.

#### Scenario: Folder/tier mismatch refused

- **WHEN** a staged sidecar declares `rights_tier: public_domain` but its target folder is `corpus/personal_library/`
- **THEN** commit refuses the item with `rights_tier '<tier>' is not permitted under '<folder>/' — move to '<expected-folder>/'` and no files move

### Requirement: Audit report

The `corpus audit` subcommand SHALL produce a read-only coverage and gate-status report in markdown (default) or JSON form. The report SHALL include:

- Total item count by folder and by rights tier
- Gate tracking against the ratified `corpus-seed` floors (item pool per side, Romanian text share, nocturne pool, B&W photography share, anchor-eligible text count, theme-coverage floor per side, resolution floor, triplet pool, triplet flavor mix, aligned-nocturne share, zero validator errors, zero `panel_verdict: reject`)
- Theme coverage table with image-side and text-side counts per theme
- Language distribution across text items
- `panel_fidelity` and `panel_verdict` distributions
- Resolution status (items below the orientation-aware floor, items below the long-edge preference)
- Outstanding `panel_verdict: reject` and `flag` items
- Mood / register / form histograms, with any out-of-taxonomy terms flagged

Exit code is always zero; audits report state, they do not fail the run.

#### Scenario: Writing an audit to file

- **WHEN** the operator runs `corpus audit --out corpus/_audits/audit-$(date +%F).md`
- **THEN** the file is written with the sections above and the output path is printed on stdout
