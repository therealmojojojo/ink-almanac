# CLAUDE.md — architecture & conventions

This file orients any contributor (human or agent) to the Inkplate repo. Read it before editing.

## What the project is

A kitchen-fridge ambient display on an Inkplate 10 e-ink panel (1200×825, 3-bit greyscale, 8 shades, no hue). A server-side pipeline picks a daily "triplet" (anchor text + summary slot + gallery slot) from a curated corpus of images and texts, renders each face as PNG, and the device polls on its own schedule. Weather, Now-Playing, Night, and Gallery faces rotate through the day.

## Runtime topology

```
corpus/         ──▶  pairing/  ──▶  pairings/  ──▶  renderer/  ──▶  PNG files
(images+texts)       (picker)       (per-day        (HTML →
                                     triplet)        rasterize)
                                                         │
                                                         ▼
                                                    HA serves PNGs
                                                         │
                                                         ▼
                                                    Inkplate 10 polls
```

- **`corpus/`** — sidecar YAML + binaries + taxonomy. Schema: `openspec/specs/corpus-schema`. Taxonomy: `openspec/specs/corpus-taxonomy`.
- **`pairing/`** — Python. Today: a validator (`corpus_validate.py`), a narrow refetcher (`corpus_refetch.py`), and the daily triplet picker (`publish_today.py`, fired by HA cron at 06:00). Pending: the full curator-side CLI (propose-list, fetch-list, prune, restore) tracked under `openspec/changes/add-ingestion-automation/` and `openspec/changes/add-pairing-pipeline/`.
- **`renderer/`** — Node/TypeScript. HTML templates per face → headless browser → PNG. Templates live in `renderer/templates/`. Output under `renderer/dist/`.
- **`firmware/`** — Inkplate 10 firmware (ESP32, PlatformIO). See `firmware/README.md`.
- **`ha/`** — Home Assistant config (secrets, automations, sensors, scripts). Real secrets never leave the operator VM; `ha/secrets.yaml` is git-ignored.
- **`openspec/`** — requirements & change management. Ratified capabilities in `openspec/specs/`; proposals in `openspec/changes/<name>/`.

## Conventions

- **Source of truth is `openspec/`.** `requirements/Requirements.md` is reference-only and carries a deprecation note at the top. Do not edit it as a design doc.
- **Corpus edits: YAML sidecars are git-tracked; binaries and `.body.<lang>.txt` files are not.** Everything non-tracked is reconstructed from `corpus/_manifest.json` + the configured backup.
- **Personal-library tier** is the EU private-copy lane for web-sourced in-copyright works. It requires a `citation` field, does not commit binaries or text bodies to git, and does not upload to operator-external backup schemes. See `openspec/specs/corpus-schema` "Rights tiers and their obligations".
- **3-bit greyscale panel** — every image has `panel_fidelity: native | robust | color-dependent`. `color-dependent` items are refused at ingestion and rejected by the validator.
- **Image resolution floor is orientation-aware.** Landscape must have `pixel_width ≥ 1080`; portrait/square must have `pixel_height ≥ 693`. Long-edge ≥ 1800 is preferred. Rationale and scenarios: `openspec/specs/corpus-schema` "Image resolution floor".
- **Taxonomy is closed.** Adding a term to `mood.yaml`, `register.yaml`, `themes.yaml`, or `form.yaml` goes through the vocabulary-amendment procedure (see `corpus/_taxonomy/README.md` and the taxonomy spec). Sidecars referencing labels instead of canonical keys are rejected.

## Working with changes

- Draft new work under `openspec/changes/<change-name>/` with `proposal.md`, `design.md`, `tasks.md`, and one `specs/<capability>/spec.md` per affected capability.
- Mark tasks `[x]` only against observable state (a file exists, a command runs, a test passes).
- Archive a change only after (a) all tasks are satisfied or explicitly marked N/A with reason, (b) `openspec validate <change>` passes, (c) deltas are merged into `openspec/specs/`.

## Validation and audit

The `corpus` CLI (install: `pip install -e pairing`) provides three subcommands today:

```sh
corpus validate                                            # structural + taxonomy + manifest
corpus validate --full                                     # + sha256 verification of every manifest entry
corpus audit                                               # read-only coverage / gate-status report
corpus audit --out corpus/_audits/audit-$(date +%F).md
corpus refetch                                             # rotate panel_verdict=reject images
corpus ingest-personal --folder <path> --citation '...'    # stage a folder of scans
corpus ingest-personal --commit --batch-id <id>            # commit after review
```

Without installing: `python3 pairing/inkplate_corpus_cli.py <subcommand>`. Validate exits 0 on pass, 1 on any error. Warnings do not fail. Audit always exits 0. Subcommands `propose-list`, `fetch-list`, `prune`, `restore` are stubs (the full curator-side ingestion automation is in flight under `openspec/changes/add-ingestion-automation/`).

## Do not

- Do not edit `requirements/Requirements.md` as a design doc.
- Do not commit binaries or body-text files under `corpus/personal_library/`.
- Do not add vocabulary terms outside the amendment procedure.
- Do not fetch `panel_fidelity: color-dependent` items into the corpus.
