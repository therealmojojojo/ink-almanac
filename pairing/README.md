# pairing/

Python tooling for the Inkplate corpus. Three subcommands today — `validate`,
`audit`, `refetch` — exposed as a unified `corpus` CLI (dispatcher at
`inkplate_corpus_cli.py`). The fetch / propose / prune / restore /
ingest-personal subcommands from `add-corpus-ingestion` are stubs that
print a pointer to the spec.

## Install / run

From the repo root:

```sh
# one-off: editable install (adds `corpus` to PATH)
pip install -e pairing

# or run without installing:
python3 pairing/inkplate_corpus_cli.py <subcommand> [...]
```

Only runtime dependency is PyYAML. The richer subcommands will add `httpx`,
`anthropic`, `pydantic`, `rich`, and `Pillow` under the `ingestion` extra.

```sh
corpus help                             # subcommand reference
corpus validate                         # structural + taxonomy + manifest
corpus validate --full                  # + sha256 of every manifest entry
corpus audit                            # markdown coverage report to stdout
corpus audit --out corpus/_audits/audit-$(date +%F).md
corpus audit --format json              # machine-readable
corpus refetch                          # retry every panel_verdict=reject image
corpus refetch <id1> <id2>              # retry specific ids
corpus refetch --dry                    # show the search plan only

# personal-library folder ingestion (stage → review → commit):
corpus ingest-personal --folder ~/Downloads/kollwitz-prints --citation 'Kollwitz, *Graphic Works*, Dover, 1969'
# edit tag placeholders under corpus/_staging/<batch-id>/sidecars/
corpus ingest-personal --commit --batch-id <batch-id>
```

## corpus_validate.py

First-pass validator. Standalone, single file, one dependency (PyYAML).

```sh
pip install pyyaml         # if not already installed
python3 pairing/corpus_validate.py          # run from repo root
python3 pairing/corpus_validate.py --full   # also verify sha256 of every manifest entry (slow)
```

What it checks:

- Every sidecar under `corpus/{images,texts,nocturne,personal_library,personal_library/nocturne}/`:
  - Required common fields (id, title, year, rights_tier, source, form, themes, mood, register, added).
  - `id` matches filename basename; no duplicates across corpus.
  - `rights_tier` is one of `public_domain` / `cc0` / `personal_library`.
  - Folder matches tier (personal-library under `personal_library/`; PD/CC0 elsewhere).
  - `source_url` required for PD/CC0; `citation` required for personal-library.
  - Themes / mood / register / form members are all in `corpus/_taxonomy/*.yaml`.
  - Image items: `artist`, `medium`, `pixel_width`, `pixel_height`, `panel_fidelity` all present; `panel_fidelity` is `native` or `robust` (never `color-dependent`); `min(width, height) >= 1200`; long edge >= 1800 (warning only).
  - Image items have a matching binary on disk (.jpg/.png/.tif/.webp).
  - Text items: `author` + one of `text` / `text_variants` / `body_files`; `language` non-empty list.
- Every triplet under `corpus/_triplets/`:
  - Required fields (anchor, summary, gallery, flavor, note, themes, added).
  - All refs point to existing items.
  - `anchor` has an anchor-eligible `form` (haiku, fragment, aphorism, quote, song-chorus, lyric).
  - `flavor` matches `gallery` type (visual-day → image, text-day → text).
  - Image slots (gallery on visual-day, image summary, aligned_nocturne) have `panel_fidelity` native or robust.
  - No duplicate slot assignments.
  - Themes are in the taxonomy.
- `_manifest.json`:
  - Every on-disk binary has a manifest entry.
  - Every manifest entry points to a file that exists on disk.
  - With `--full`: sha256 matches.

Exit code is 0 if no errors, 1 otherwise. Warnings do not fail the run.

## corpus_audit.py

Read-only coverage / gate-status report. Safe to run anytime; never fails.

```sh
python3 pairing/corpus_audit.py                                         # markdown to stdout
python3 pairing/corpus_audit.py --out corpus/_audits/audit-YYYY-MM-DD.md  # write to file
python3 pairing/corpus_audit.py --format json                           # machine-readable
```

Sections:
- Folder × tier breakdown
- Gate tracking: 300 + 300, Romanian text share (≥25% floor), nocturne pool (≥30 floor), zero `panel_verdict=reject`, zero images below resolution floor
- Theme coverage by side, with a per-side ≥ 15 floor marked ✅ / ⚠️ / ∅
- Language distribution across text items
- `panel_fidelity` and `panel_verdict` distributions
- Resolution: items below floor, below long-edge preference, missing dimensions
- Outstanding `panel_verdict: reject` and `flag` items with reasons
- Mood / register / form histograms (marks any term not in the taxonomy)

Exit code is always 0.

## corpus_refetch.py

Re-fetch images whose sidecar carries `panel_verdict: reject`, walking three free sources in order (Wikimedia Commons → ARTIC → Met Open Access). Strict artist+title matching and a short-edge ≥ 1200 floor. See the file header for usage.

## corpus_review.py — triplet review tool

```sh
# Renderer in one terminal, reviewer in another:
cd renderer && npm run dev
corpus review                                # default port 8081
corpus review --only-unreviewed              # incremental review across sessions
corpus review --start <triplet-id>           # jump to a specific triplet
```

Walks `corpus/_triplets/`, stages each into the renderer, opens an
in-browser review UI showing the live Summary / Weather / Gallery /
Night previews, and captures a verdict back to the triplet sidecar:
`triplet_verdict: keep | reject-content | reject-layout` plus
`triplet_verdict_reason`.

⚠️ Each navigation rewrites `renderer/inputs/pairing.json` — meaning
the live device's next Full will display whatever triplet was last
staged. After a review session, run `python3 pairing/publish_today.py`
to restore today's actual triplet.

See [`docs/review.md`](docs/review.md) for the full reference,
keyboard shortcuts, and the `/sim` device simulator view.

## What it does NOT do yet

- Fetch binaries or body files from the web.
- Propose canonical lists via Claude.
- Check `pixel_width` / `pixel_height` match the actual binary (would need Pillow; trusted for now).
- Backfill missing fields. Reports what's wrong; you fix the YAML.
- Validate the `openspec/changes/build-seed-corpus/lists/*.yaml` proposal files. Those are operator-review artifacts, not ingested sidecars.
