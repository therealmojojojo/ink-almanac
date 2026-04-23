# Corpus ingestion workflow

Operator-facing walkthrough. Covers the **current** manual-plus-scripts workflow (what you actually do today) and the **target** `corpus` CLI (what `openspec/changes/add-corpus-ingestion/` specifies). The seed corpus was built under the current workflow; when the target CLI lands, the steps become commands.

## Concepts

- **Canonical list** — a proposal file (`openspec/changes/build-seed-corpus/lists/<name>.yaml`) enumerating works to ingest for a category. One list per `corpus propose-list` call, in the target flow.
- **Batch** — one execution of `fetch-list` against a single canonical list. Produces sidecars + binaries + a contact sheet + a batch report under `corpus/_staging/<batch-id>/`.
- **Contact sheet** — a thumbnail grid (images) or excerpt list (texts) the operator reviews after fetch to decide which items to keep or ban.
- **Rights tier** — `public_domain`, `cc0`, or `personal_library`. The tier determines folder, git behaviour, and backup routing. See `openspec/specs/corpus-schema/` "Rights tiers and their obligations".

## The `corpus` CLI

Install once from the repo root:

```sh
pip install -e pairing
```

Five subcommands are implemented: `corpus validate`, `corpus audit`, `corpus refetch`, `corpus ingest-personal`, `corpus restore`. The automation layer (`propose-list`, `fetch-list`, `prune`, `propose-triplets`, …) lives in the follow-on change `add-ingestion-automation`.

### Single-item ingestion (dominant path)

In practice, most items land via agent-driven direct authoring:

1. Operator supplies a URL or plain-language reference.
2. The agent identifies the work, picks the highest-resolution copy that meets the resolution floor, and writes a complete sidecar (taxonomy-compliant tags, `panel_fidelity`, `citation`, etc.) into the correct tier folder.
3. Manifest entry is appended.

`corpus validate` on the result must pass. There is no TODO-tag phase; the sidecar is complete at write time.

### `corpus ingest-personal` (folder-mode batch — two-phase)

For pre-assembled folders of web downloads or typed-text fragments:

**Stage.** Copies files into `corpus/_staging/<batch-id>/` and writes sidecar skeletons with every mandatory field present. Image dimensions come from Pillow. Tag fields are authored by the agent in the same pass — not left as placeholders for the operator.

```sh
corpus ingest-personal --folder ~/Downloads/dinescu-selected \
    --citation 'Dinescu, *Opere*, Humanitas, 2004' \
    [--nocturne] [--language ro] [--source-url https://...] [--id-prefix dinescu-]
```

**Commit.** Validates every staged sidecar, moves into `corpus/personal_library/[nocturne/]`, and appends manifest entries with `file://` backup URIs by default (`--backup-scheme icloud` for iCloud Drive; cloud schemes are refused for personal-library):

```sh
corpus ingest-personal --commit --batch-id <batch-id>
```

The commit step enforces the orientation-aware resolution floor (landscape ≥ 1080 width, portrait/square ≥ 693 height), refuses `panel_fidelity: color-dependent`, and refuses to overwrite existing item ids. As a safety net, if a staged sidecar was left with placeholder tags, commit reports the specific fields and refuses to move the batch.

If you prefer not to install, every subcommand also works as `python3 pairing/inkplate_corpus_cli.py <subcommand> ...`.

## Current workflow (as of 2026-04-18)

### 1. Author a canonical list (manual)

Drop a YAML file into `openspec/changes/build-seed-corpus/lists/<name>.yaml`:

```yaml
category: hokusai-manga
rights_tier_default: public_domain
items:
  - id: hokusai-manga-waves
    title: "Waves (Hokusai Manga)"
    artist: "Katsushika Hokusai"
    source_hints:
      - "https://commons.wikimedia.org/wiki/File%3AHokusai_Manga_-_Waves.jpg"
    panel_fidelity: native
    themes: [water-and-reflection, japan]
    ...
```

Review the list against the taste file (`openspec/changes/build-seed-corpus/taste.md`) and the native-B&W pivot rule (`openspec/changes/build-seed-corpus/lists/RETIRED.md`) before executing. **This is the curatorial gate** — approve at list level, not post-fetch.

### 2. Fetch (manual / ad-hoc)

Pull each binary from the hinted source with any tool (browser + Preview save, curl, `wget`). Place it under:

- `corpus/images/<id>.jpg` for PD / CC0 visual works.
- `corpus/nocturne/<id>.jpg` for PD / CC0 night-mode visuals.
- `corpus/personal_library/<id>.jpg` for in-copyright web-sourced images (tier: `personal_library`).
- `corpus/personal_library/nocturne/<id>.jpg` for night-mode personal-library images.

Text items are authored as sidecars only — no binary. Place under `corpus/texts/<id>.yaml` (PD) or `corpus/personal_library/<id>.yaml` (personal library). Use the `EXAMPLE*.yaml.template` sidecars in those folders as skeletons.

Read real `pixel_width` / `pixel_height` from the binary (e.g., `sips -g pixelWidth -g pixelHeight <file>` or `identify <file>`). Declare `panel_fidelity`: `native` for pure-value media, `robust` for tonally strong color-origin work. Never `color-dependent` — drop the item instead.

Add an entry to `corpus/_manifest.json`:

```json
{
  "path": "corpus/images/<id>.jpg",
  "sha256": "<sha256sum output>",
  "bytes": <ls -l bytes>,
  "mime": "image/jpeg",
  "backup_uri": "file:///absolute/path/to/corpus/images/<id>.jpg"
}
```

### 3. Validate

```sh
python3 pairing/corpus_validate.py
```

Fix errors (missing fields, unknown taxonomy tags, tier/folder mismatches, short-edge failures) before moving on. Warnings (long-edge < 1800 preferred, `panel_verdict: flag`) are informational.

### 4. Refetch rejects (optional)

For items marked `panel_verdict: reject` whose rejection was a fetch failure (wrong artwork, too low resolution), rotate through free sources:

```sh
python3 pairing/corpus_refetch.py                  # all rejects
python3 pairing/corpus_refetch.py <id1> <id2>      # specific ids
python3 pairing/corpus_refetch.py --dry            # show plan only
```

Items the script can't fix (no free high-res copy exists, wrong subject returned, defective source) stay marked `reject`. The curatorial options are: substitute a comparable work from the same category, replace with a higher-resolution source once discovered, or drop the item. There is no scanning path.

### 5. Audit

```sh
python3 pairing/corpus_audit.py --out corpus/_audits/audit-$(date +%F).md
```

Read the gate table and theme-coverage table. Log any thin themes or floor misses in `openspec/changes/build-seed-corpus/log.md` and plan the next canonical list to fill the gap.

### 6. Triplets (curatorial, not ingestion)

Triplet authoring happens against the stable pool — one triplet per YAML under `corpus/_triplets/`. See `openspec/specs/corpus-triplets/` (via the schema change). Triplets reference items by `id`; the validator ensures refs resolve, anchors are anchor-eligible, and image slots are `native` or `robust`.

## Target workflow (once `corpus` CLI lands)

The target state turns the manual steps into subcommands of a single `corpus` entry point. Each step below maps directly to an unfinished task in `openspec/changes/add-corpus-ingestion/tasks.md`.

| Step | Current | Target command |
|---|---|---|
| Author a list | Hand-write YAML with taste review | `corpus propose-list --category <name> --out <path>` |
| Fetch | Manual download + place file + edit `_manifest.json` | `corpus fetch-list --file <path>` |
| Contact sheet | Inspect files manually | Generated automatically under `corpus/_staging/<batch-id>/contact-sheet.html` |
| Prune | Delete files + manifest entries by hand | `corpus prune --batch <id> --ban <ids>` |
| Retry failed fetches | `corpus_refetch.py` (images only) | `corpus fetch-binaries --batch <id>` |
| Folder-mode ingest (web downloads, typed text) | `corpus ingest-personal --folder <path> --citation <string>` (stage → review → commit; tags authored by operator) | same, with optional `--claude-tag` assist |
| Validate | `corpus validate` | same |
| Audit | `corpus audit` | same |
| Refetch rejects | `corpus refetch` | `corpus fetch-binaries --batch <id>` |
| Restore from backup | Not implemented | `corpus restore` |

## Configuration (target)

| Setting | Purpose | Current default |
|---|---|---|
| `CORPUS_BACKUP_SCHEME` | Default backup URI scheme: `file://`, `icloud://`, `b2://`, `s3://` | `file://` |
| `CORPUS_BACKUP_BASE` | Root of the backup location | Repo-local path |
| `CORPUS_SEARCH_BACKEND` | Web search backend for personal-library acquisition (`brave`, `bing`, `serpapi`) | unset |
| `ANTHROPIC_API_KEY` | Credentials for `corpus propose-list` | unset |
| `B2_*` / `AWS_*` / etc. | Credentials for cloud backup schemes | unset |

Personal-library content SHALL route to operator-controlled schemes (`file://`, `icloud://`) unless the operator explicitly opts into cloud schemes per `corpus-schema` "Rights tiers".

## Rights-tier checklist

Every item must answer all three:

1. **What tier?** PD / CC0 / personal-library — determines folder.
2. **Is the source authoritative?** PD/CC0 needs a `source_url` to an institutional record or a CC0 declaration. Personal-library needs a `citation` to a canonical published source.
3. **Does the backup route stay under operator control?** Personal-library: `file://` or `icloud://` only (unless the operator opted in otherwise).

A personal-library binary must never enter the git index — `.gitignore` covers it, and the precommit check (when wired) refuses staging.
