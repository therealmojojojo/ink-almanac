## Why

The corpus is the soul of the dashboard. `add-corpus-schema` ratified what a corpus item looks like; this change adds the tooling that lets the operator actually assemble one. Without ingestion tooling, every downstream capability that depends on the corpus stalls.

This change is deliberately scoped to the tooling that proved load-bearing during `build-seed-corpus`: validation, coverage audit, folder-mode ingestion, a narrow refetcher for reject rescue, manifest-driven restore, and rights-tier routing across all of these. The agent-assisted canonical-list proposal / fetch-list / prune / triplet-proposal flows are spun into a separate follow-on change, `add-ingestion-automation`, because they were never built or exercised during the seed.

## What Changes

- Introduce a Python ingestion CLI under `pairing/` (shared Python toolchain with the pairing pipeline), installable as `corpus` via a `pyproject.toml` entry point.
- Implement **`corpus validate`** (structural + taxonomy + manifest checks; `--full` verifies sha256 of every manifest entry).
- Implement **`corpus audit`** (read-only coverage / gate-status report; markdown or JSON).
- Implement **`corpus refetch`** (rotates image items flagged `panel_verdict: reject` through Wikimedia Commons → ARTIC → Met Open Access at the `corpus-schema` resolution floor).
- Implement **`corpus ingest-personal`** as a two-phase stage → commit workflow for folder ingestion of web-downloaded images or typed text fragments. Dominant single-item usage is agent-driven: the agent identifies a work from an operator-supplied URL, authors the complete sidecar with taxonomy-compliant tags, and commits. TODO-placeholder staging exists as a safety net, not a workflow expectation for the operator.
- Implement **`corpus restore`**: reads `_manifest.json`, fetches missing content bodies from `backup_uri`, verifies sha256 on every restored file, halts on mismatch. Supports `file://` and `icloud://`.
- Implement **validation at the boundary**: every sidecar written by any of the above subcommands validates against `corpus-schema` + `corpus-taxonomy` before the write commits.
- Define the **backup URI format** for `_manifest.json` entries and enforce **rights-tier routing** (personal-library restricted to `file://` / `icloud://` unless operator opts in).

Not in this change (moved to `add-ingestion-automation`):

- `corpus propose-list` (Claude-authored canonical list files)
- `corpus fetch-list` (end-to-end list execution with PD connectors + web-search channel)
- `corpus prune` (contact-sheet-driven batch pruning)
- Dedicated PD-connector modules (Rijksmuseum, Gallica BnF, LoC, Project Gutenberg, Wikisource) beyond the Commons / ARTIC / Met triad used by `refetch`
- Web-search backend abstraction with reputable-domain preference
- `corpus propose-triplets` / `review-triplets` / `commit-triplets`
- Pydantic model layer
- Per-batch contact-sheet and report generation
- Claude-tagging hook inside `ingest-personal`
- Upload-to-backup at fetch time

## Capabilities

### New Capabilities

- `corpus-ingestion`: the tooling boundary for writing items into the corpus — validation, audit, narrow refetch, folder-mode stage/commit, direct sidecar authoring, manifest-driven restore, and rights-tier routing.

### Modified Capabilities

None.

## Impact

- Affected code: `pairing/` (new / updated files: `inkplate_corpus_cli.py`, `corpus_validate.py`, `corpus_audit.py`, `corpus_refetch.py`, `corpus_ingest_personal.py`, `corpus_restore.py`, `pyproject.toml`, `README.md`, `docs/ingestion-workflow.md`).
- Affected docs: root `CLAUDE.md`, `corpus/README.md`, `corpus/_manifest.README.md`, `corpus/_taxonomy/README.md`, `corpus/_taxonomy/validation.md`, and EXAMPLE sidecar templates under `corpus/images/`, `corpus/texts/`, `corpus/personal_library/`.
- Runtime deps: `pyyaml` (validation / ingest / audit / refetch / restore), `Pillow` (ingest-personal reads real pixel dims). Richer deps (`httpx`, `anthropic`, `pydantic`, `rich`) are declared under the optional `ingestion` extra for the follow-on change.
