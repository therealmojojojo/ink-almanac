## 1. Package scaffolding

- [x] 1.1 `pairing/pyproject.toml` with `[project.scripts] corpus = "inkplate_corpus_cli:main"` — `pip install -e pairing` exposes `corpus` on PATH.
- [x] 1.2 Runtime deps declared (`pyyaml` hard; `httpx` / `anthropic` / `pydantic` / `rich` / `Pillow` behind optional `ingestion` extra — Pillow is actually used by `ingest-personal` today; the rest ride the follow-on).
- [x] 1.3 Flat module layout: `inkplate_corpus_cli.py` dispatcher + `corpus_validate.py` / `corpus_audit.py` / `corpus_refetch.py` / `corpus_ingest_personal.py` / `corpus_restore.py`. The nested `src/inkplate/ingestion/...` tree was deferred to follow-on when module size warrants subpackages.

## 2. Validation

- [x] 2.1 `corpus validate` — field-level required-field / type / tier-specific obligation checks
- [x] 2.2 Taxonomy-membership validation (themes / mood / register / form)
- [x] 2.3 Tier/folder consistency (personal-library under `personal_library/`; PD/CC0 elsewhere; no-inline-text rule; body_files resolution)
- [x] 2.4 Manifest ↔ filesystem consistency (bidirectional); `--full` verifies sha256
- [x] 2.5 Wired as `corpus validate [--full]` subcommand

## 3. Audit

- [x] 3.1 Read-only coverage / gate-status report per `corpus-seed` floors
- [x] 3.2 Folder × tier breakdown, language distribution, panel_fidelity / panel_verdict distributions, resolution status, tag histograms
- [x] 3.3 Theme-coverage table with per-side counts and the ratified `≥ 10 per side` floor
- [x] 3.4 `--format md|json`, `--out <path>`, always exits zero
- [x] 3.5 Wired as `corpus audit` subcommand

## 4. Refetch (narrow reject-rescue)

- [x] 4.1 `corpus refetch` rotates `panel_verdict: reject` image items through Wikimedia Commons → ARTIC → Met Open Access
- [x] 4.2 Strict artist+title token matching to prevent wrong-artwork fetches
- [x] 4.3 Enforces short-edge ≥ 1200 px at download time; candidates below the floor discarded
- [x] 4.4 `[ids...]` to target specific items; `--dry` to preview without writing
- [x] 4.5 Wired as `corpus refetch` subcommand

## 5. Personal-library folder-mode ingestion

- [x] 5.1 `corpus ingest-personal --folder <path> --citation "<string>"` stages files under `corpus/_staging/<batch-id>/`
- [x] 5.2 Accepts image files (jpg/jpeg/png/tif/tiff/webp) and text files (.txt/.md); Pillow reads real dimensions at stage time
- [x] 5.3 `--commit --batch-id <id>` validates against schema + taxonomy, enforces orientation-aware resolution floor, refuses `panel_fidelity: color-dependent`, refuses overwrite of existing ids, moves into `corpus/personal_library/[nocturne/]`, appends manifest entries
- [x] 5.4 Backup-scheme flag (`file` default, `icloud` permitted); `b2` / `s3` refused for the personal-library tier
- [x] 5.5 `--nocturne`, `--language`, `--source-url`, `--id-prefix`, `--dry-run` flags
- [x] 5.6 Exercised end-to-end during development (synthetic fixture with valid + below-floor + TODO-placeholder sidecars; each path verified)

## 6. Restore from manifest

- [x] 6.1 `corpus restore` reads `_manifest.json`, fetches missing content bodies from `backup_uri`
- [x] 6.2 `file://` scheme supported (direct copy)
- [x] 6.3 `icloud://` scheme supported (resolved against `INKPLATE_ICLOUD_ROOT`)
- [x] 6.4 `b2://` / `s3://` recognised but not implemented — skipped with a diagnostic
- [x] 6.5 Sha256 verified post-copy; mismatches halt the per-item restore and leave the file absent
- [x] 6.6 `--check` (read-only state report), `--verify` (re-verify sha256 of every existing file), `--force` (overwrite), positional paths (restrict scope)
- [x] 6.7 Exercised end-to-end via an accidental corpus-binary deletion during development; round-trip against the authoritative source (ARTIC) produced a sha256-matching file

## 7. Rights-tier routing

- [x] 7.1 `ingest-personal` refuses to place `rights_tier: personal_library` items outside `corpus/personal_library/`
- [x] 7.2 `ingest-personal` refuses to place `public_domain` / `cc0` items under `corpus/personal_library/`
- [x] 7.3 Personal-library backup routing limited to `file://` / `icloud://` by default at both ingest and restore
- [x] 7.4 `.gitignore` rules at repo root cover personal-library binaries and `.body.<lang>.txt` files

## 8. Documentation

- [x] 8.1 `pairing/README.md` describes all five implemented subcommands with example invocations
- [x] 8.2 `pairing/docs/ingestion-workflow.md` operator walkthrough — current workflow, tool options, rights-tier checklist, configuration
- [x] 8.3 Backup-scheme configuration documented in `pairing/docs/ingestion-workflow.md` and `corpus/_manifest.README.md`
- [x] 8.4 `CLAUDE.md` at repo root references the `corpus` CLI and its subcommands

## 9. Integration

- [x] 9.1 `corpus validate` runs clean on a fully-populated corpus (demonstrated at `build-seed-corpus` archive: 0 errors over 404 sidecars, 301 triplets, 192 manifest entries)
- [x] 9.2 `corpus audit` gate tracking used as the archive-readiness check for `build-seed-corpus`
- [x] 9.3 `corpus refetch` used against real reject items during seed assembly
- [x] 9.4 `corpus ingest-personal` exercised end-to-end (stage → edit → commit) on a synthetic fixture
- [x] 9.5 `corpus restore` exercised against ARTIC for a sha256-matching round-trip
