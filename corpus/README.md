# corpus/

Curated works — images and texts — plus the controlled vocabulary they reference and a manifest of the binaries that aren't in git.

Authoritative schema and taxonomy live in `openspec/specs/corpus-schema/` and `openspec/specs/corpus-taxonomy/`. This README is a human-readable companion; on any conflict the specs win.

## Folder layout

```
corpus/
├── images/                  public-domain / CC0 images (everyday rotation)
├── texts/                   public-domain / CC0 texts (inline YAML)
├── nocturne/                night-mode image pool (PD / CC0), separate rotation
├── personal_library/        in-copyright works admitted under the private-copy tier
│   └── nocturne/            personal-library night-mode images
├── _taxonomy/               controlled vocabulary (themes / mood / register / form)
├── _manifest.json           binary inventory with sha256 + backup_uri
├── _staging/                per-batch contact sheets + reports (git-ignored)
├── _audits/                 generated audit reports
└── _triplets/               anchor+summary+gallery groupings (curatorial artefacts)
```

Each work is exactly two files sharing a kebab-case basename:

- `images/`, `nocturne/`, `personal_library/` — `<id>.yaml` + `<id>.(jpg|png|tif|tiff|webp)`.
- `texts/`, and text items under `personal_library/` — `<id>.yaml` only; the text body lives inline in the sidecar.

`id` is unique across the entire corpus and stable for the lifetime of the item — renaming a file basename is treated as removal + addition (see spec "Stable identifiers").

## Rights tiers

Every sidecar declares exactly one `rights_tier`:

| Tier | Meaning | Obligations |
|---|---|---|
| `public_domain` | Verifiably PD worldwide or in the EU | `source_url` resolves to an authoritative record |
| `cc0` | Released under CC0 | `source_url` resolves to the CC0 declaration |
| `personal_library` | In-copyright work admitted under the EU private-copy exception (Romania Law 8/1996 Art. 34) for display on the operator's own device | Requires `citation`; binaries and `.body.<lang>.txt` files are git-ignored; SHALL NOT be distributed beyond the household; backup routes only to operator-controlled storage (`file://`, `icloud://`) |

The tier must match the folder. A `personal_library` item in `corpus/images/` is rejected by the validator with a pointer to `corpus/personal_library/`. See `openspec/specs/corpus-schema/` "Rights tiers and their obligations".

### Personal-library specifics

- Acquisition is by fetching a publicly visible reproduction or text from a third-party source (museum, artist estate, literary archive, publisher preview, poetry site, etc.). The `citation` field still names a canonical published source for the work; it identifies what the item is, not where the file came from.
- `citation` format: `"<Author>, *<Book Title>*, <Publisher>, <Year>, page <N>"` — the bibliographic reference to a canonical published source.
- Binaries and text bodies are never committed to git and never uploaded to backup schemes that leave the operator's control. Pre-commit will refuse a personal-library binary in the index.

## Adding a new item

1. Pick the right folder (tier + night vs. day + images vs. texts).
2. Choose a kebab-case `id` that's unique corpus-wide. Prefer `<maker>-<short-title>`.
3. Drop the binary (for images) into the folder with basename `<id>.(jpg|png|...)`. Do not commit it — it goes into the manifest.
4. Write `<id>.yaml` following the spec. All tags (`themes`, `mood`, `register`, `form`) must be canonical keys present in `corpus/_taxonomy/*.yaml`. Labels, capitalised variants, or new terms are rejected.
5. Image items must record real `pixel_width` / `pixel_height` and declare `panel_fidelity` (`native` / `robust`; `color-dependent` items must not enter the corpus).
6. Run the validator:

   ```sh
   python3 pairing/corpus_validate.py
   ```

7. Add an entry to `_manifest.json` for every binary and body file (or let the ingestion tool do this once it exists).
8. See `corpus/images/EXAMPLE.yaml.template`, `corpus/texts/EXAMPLE.yaml.template`, `corpus/texts/EXAMPLE-BILINGUAL.yaml.template`, and `corpus/personal_library/EXAMPLE.yaml.template` for complete, annotated skeletons.

## Taxonomy and amendments

Tag vocabulary is closed. Adding or deprecating a term goes through the amendment procedure in `corpus/_taxonomy/README.md`. Do not silently widen the vocabulary from a sidecar — the validator will reject it and the amendment flow records the rationale.

## Panel-fidelity constraint

The Inkplate 10 panel is 3-bit greyscale (8 shades, no hue). Every image sidecar declares `panel_fidelity`:

- `native` — conceived under a pure-value constraint (etching, engraving, pen-and-ink, charcoal, ink-wash, monochrome litho, B&W photography). Full fidelity.
- `robust` — color-origin but tonally self-sufficient (a tonally strong painting, a Hiroshige snow scene). Approved at list-review.
- `color-dependent` — figure/ground or mood carried by hue/saturation. Refused at ingestion and rejected by the validator.

After hardware review an image may additionally carry `panel_verdict: keep | flag | reject` plus `verdict_reason` and `verdict_reviewed_at`.

## Manifest

`_manifest.json` enumerates every content body that isn't in git (image binaries, optional body-text files). See `_manifest.README.md` for the schema. The validator checks that the manifest and filesystem agree; `--full` additionally verifies sha256.

## What's tracked vs. ignored

The operator's actual corpus — sidecars, triplets, audits, manifest — is gitignored. A fresh clone has only:

- `_taxonomy/` — controlled vocabulary (tracked; amendments go through the procedure documented there).
- `EXAMPLE.yaml.template` files in `images/`, `texts/`, `personal_library/`, and `_triplets/` — annotated skeletons.
- This README and `_manifest.README.md`.

Forks build their own corpus from these primitives. Specifically:

```
images/*.yaml                tracked? no    (operator-curated)
texts/*.yaml                 tracked? no
personal_library/*.yaml      tracked? no
_triplets/*.yaml             tracked? no    (regenerated artefact)
_audits/*.md                 tracked? no    (generated reports)
_caches/*                    tracked? no    (intermediate caches)
_manifest.json               tracked? no    (binary inventory; rebuilt locally)
```

If you're authoring a sidecar, write it directly under the right folder — `.gitignore` will keep it out of commits.

## Building a corpus from scratch

The directory tree above is enough to bootstrap. Two flows produce sidecars:

1. **Photographer / artist harvest** (image-heavy, web-sourced).

   ```sh
   pip install -e pairing
   corpus harvest <creator-id>          # phase 1: candidate scrape + contact sheet
   # operator reviews corpus/_staging/harvest-<creator-id>/decisions.yaml
   corpus harvest --commit <creator-id> # phase 2: vision-tag + write sidecars (in flight)
   ```

   Phase 1 is implemented and writes a staging report under `corpus/_staging/`. Phase 2 (vision-tag → sidecar → manifest) lands with `openspec/changes/add-ingestion-automation`. Until then, sidecars from a phase-1 staging dir are written by hand using the EXAMPLE template, then validated.

2. **Personal library ingest** (web-sourced reproductions of in-copyright works, EU private-copy tier).

   ```sh
   corpus ingest-personal --folder /path/to/scans \
                          --citation '<Author>, *<Title>*, <Publisher>, <Year>'
   # review staging
   corpus ingest-personal --commit --batch-id <id>
   ```

   See `openspec/specs/corpus-schema` "Rights tiers and their obligations" for what `personal_library` requires.

After either flow, validate:

```sh
corpus validate          # structural + taxonomy + manifest agreement
corpus validate --full   # + verify sha256 of every binary against the manifest
corpus audit             # coverage report (themes / register / panel-fidelity mix)
```

## Building the triplet pool

`_triplets/` is a generated artefact, not authored by hand. Once the corpus has enough texts and images, run:

```sh
python pairing/corpus_build_triplets_v2.py           # dry-run; prints counts and rules summary
python pairing/corpus_build_triplets_v2.py --apply   # wipe and regenerate _triplets/
```

The generator enforces the rules documented at the top of `corpus_build_triplets_v2.py` (wrap-aware summary eligibility, 65/35 visual/text gallery split, per-item cap of 5, 100-position recency window, etc.). Existing `triplet_verdict` annotations on surviving ids are preserved.

After regenerating, review the pool in the browser:

```sh
cd renderer && npm run dev
# new shell:
corpus review                         # all triplets
corpus review --only-unreviewed       # skip already-judged ones
```

Each triplet's faces (Summary / Weather / Gallery / Night) are rendered live and you can keep / reject-content / reject-layout per triplet. Verdicts write back to the triplet sidecar.

## Daily rotation

Once `_triplets/` is populated, `pairing/publish_today.py` walks them in `sequence` order, one per day, anchored at the date in `pairing/_state/triplet_epoch.json`. The epoch file is created on first run; delete it (or edit the date) to re-anchor the rotation back to sequence 1. HA fires this script daily at 06:00 via `shell_command.publish_today_pairing`.
