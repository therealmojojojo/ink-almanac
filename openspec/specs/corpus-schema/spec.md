# corpus-schema Specification

## Purpose
TBD - created by archiving change add-corpus-schema. Update Purpose after archive.
## Requirements
### Requirement: Corpus filesystem layout

The corpus SHALL be stored under a top-level `corpus/` directory with the following subdirectories:

- `corpus/images/` — visual works, public domain or CC0 tier
- `corpus/texts/` — textual works, public domain or CC0 tier
- `corpus/nocturne/` — visual works reserved for the Night mode, separate rotation pool
- `corpus/personal_library/` — works admitted under the personal-library tier (scans from privately owned books)
- `corpus/_taxonomy/` — controlled vocabulary files (themes, mood, register, form)
- `corpus/_manifest.json` — binary inventory with checksums for restore

Each work SHALL consist of exactly two files sharing the same basename: the binary (image or embedded text) and a `.yaml` sidecar. The basename SHALL be a kebab-case identifier unique across the entire corpus.

#### Scenario: Valid image item layout

- **WHEN** a new image is added under `corpus/images/` with basename `hiroshige-shin-ohashi`
- **THEN** the corpus contains `corpus/images/hiroshige-shin-ohashi.jpg` (or `.png`/`.tif`/`.webp`) and `corpus/images/hiroshige-shin-ohashi.yaml`, and no other file shares that basename anywhere under `corpus/`

#### Scenario: Text item with embedded content

- **WHEN** a text work is added under `corpus/texts/` with basename `basho-old-pond`
- **THEN** the corpus contains `corpus/texts/basho-old-pond.yaml` with the text embedded in the sidecar itself (no separate binary), and ingestion tooling accepts this as a complete item

### Requirement: Sidecar schema — common fields

Every sidecar `.yaml` SHALL include the following top-level fields:

- `id` — string, matches the file basename
- `title` — string, the work's title in its original language; empty string allowed only for untitled works
- `year` — integer or ISO date string; `null` allowed for unknown provenance
- `rights_tier` — one of `public_domain`, `cc0`, `personal_library`
- `source` — identifier of the institution or source (e.g., `met_open_access`, `rijksmuseum`, `gallica_bnf`, `loc_pnp`, `wikimedia_commons`, `project_gutenberg`)
- `source_url` — URL to the canonical record; `null` allowed only when `rights_tier: personal_library`
- `citation` — string, required when `rights_tier: personal_library`; format "<Author>, *<Book Title>*, <Publisher>, <Year>, page <N>"
- `themes` — non-empty array of strings, each member present in `corpus/_taxonomy/themes.yaml`
- `mood` — non-empty array of strings, each member present in `corpus/_taxonomy/mood.yaml`
- `register` — non-empty array of strings, each member present in `corpus/_taxonomy/register.yaml`
- `form` — string, present in `corpus/_taxonomy/form.yaml`
- `language` — array of ISO 639-1 codes for text works (e.g., `[en]`, `[ro]`, `[en, ro]`); `null` or omitted for images
- `added` — ISO date string, when the item entered the corpus

#### Scenario: Sidecar passes validation

- **WHEN** a sidecar includes all required fields with values present in the relevant taxonomy file
- **THEN** corpus validation reports the item as valid

#### Scenario: Sidecar uses an unknown tag

- **WHEN** a sidecar includes a mood value not present in `corpus/_taxonomy/mood.yaml`
- **THEN** corpus validation rejects the item with an error naming the offending value and the field it belongs to

#### Scenario: Personal-library item missing citation

- **WHEN** a sidecar declares `rights_tier: personal_library` without a `citation` field
- **THEN** corpus validation rejects the item with an error stating that personal-library items require a book citation

### Requirement: Sidecar schema — work-type fields

Sidecars SHALL include work-type-specific fields:

**Image items** additionally SHALL include:
- `artist` — string, the maker's name; empty string allowed for anonymous works
- `medium` — string (e.g., `woodblock print`, `silver gelatin photograph`, `etching`)
- `pixel_width` — integer, the width of the stored binary in pixels
- `pixel_height` — integer, the height of the stored binary in pixels
- `panel_fidelity` — one of `native`, `robust`, `color-dependent` (see "Panel fidelity" requirement below)
- `panel_verdict` — optional; one of `keep`, `flag`, `reject`. Visual-review outcome after the image has been rendered through the gallery template and assessed for crispness, contrast, composition, and correct-artwork identity. `reject` means the item is unsuitable for the panel in its current form (wrong artwork matched at fetch, faded scan, heavy scan-artifact border, etc.) and MUST NOT be used in triplet slots. `flag` means marginal — kept on disk but flagged for operator reconsideration. Absence means unreviewed.
- `verdict_reason` — optional string, required when `panel_verdict` is `flag` or `reject`. Short explanation of why the verdict was given.
- `verdict_reviewed_at` — optional ISO date, when the visual review was recorded.

`pixel_width` and `pixel_height` SHALL be populated by ingestion from the binary's actual dimensions (not trusted user input); corpus validation SHALL reject any image whose recorded dimensions disagree with the on-disk binary.

**Text items** additionally SHALL include:
- `author` — string
- One of `text` or `text_variants`, regardless of tier:
  - `text` — string, the verbatim text in a single language
  - `text_variants` — map from ISO 639-1 code to string, for bilingual or translated works

Text bodies SHALL be stored inline in the sidecar YAML for all tiers. Sibling body files (`<id>.body.<lang>.txt`) are permitted as an optional operational convenience for very long texts where inline YAML escaping becomes unwieldy, but are not required and not the default.

#### Scenario: Image item without artist field

- **WHEN** a sidecar under `corpus/images/` or `corpus/nocturne/` or `corpus/personal_library/` lacks an `artist` field
- **THEN** corpus validation rejects the item

#### Scenario: Text item with bilingual variants

- **WHEN** a text sidecar declares `text_variants: { en: "...", ro: "..." }` and `language: [en, ro]`
- **THEN** corpus validation accepts the item and the pairing pipeline MAY present either variant

#### Scenario: Personal-library text item with inline text

- **WHEN** a sidecar under `corpus/personal_library/` declares `rights_tier: personal_library`, `language: [ro]`, and carries `text_variants: { ro: "..." }` inline
- **THEN** corpus validation accepts the item

### Requirement: Image resolution floor

Every image item — in `corpus/images/`, `corpus/nocturne/`, or `corpus/personal_library/` — SHALL satisfy a minimum pixel-dimension floor chosen against the Inkplate 10 panel (1200×825 native) under orientation-aware matted display:

- **MUST (landscape images where width > height)**: `pixel_width ≥ 1080`. Landscape images fill the panel width; after a ~60 px mat inset the image box is ~1080 px wide.
- **MUST (portrait or square images where height ≥ width)**: `pixel_height ≥ 693`. Portrait/square images fill the panel height (pillarboxed with L/R mat); after mat inset the image box is ~693 px tall.
- **SHOULD**: `max(pixel_width, pixel_height) ≥ 1800`. A long-edge margin gives server-side Lanczos resampling (when introduced) headroom to preserve edge detail through downscale.

Rationale: under the orientation-aware matted rendering (see `rendering-pipeline`), only the fill-axis is scaled to fit the panel. Requiring the *short* edge to reach 1200 — the panel's long edge — is over-strict; the browser never upscales the non-fill axis. The legacy `short_edge ≥ 1200` rule applied to `object-fit: cover` mode.

Corpus validation SHALL reject any image item whose fill-axis falls below the MUST floor. Ingestion SHALL treat any candidate below the floor as a fetch-failure and rotate to the next candidate (see `corpus-ingestion`).

These dimensions refer to the stored binary, not any decorative render step. Cropping that reduces the fill-axis below the floor is not acceptable; the source should be re-fetched at higher resolution instead.

#### Scenario: Portrait image meets orientation-aware floor

- **WHEN** an image sidecar records `pixel_width: 853`, `pixel_height: 1280` (portrait)
- **THEN** corpus validation accepts the item: fill-axis is height = 1280, exceeds the 693 portrait floor

#### Scenario: Landscape image fails orientation-aware floor

- **WHEN** an image sidecar records `pixel_width: 1028`, `pixel_height: 1536`... actually height exceeds width, so it's portrait: fill-axis = 1536, passes

#### Scenario: Image legitimately too small

- **WHEN** an image records `pixel_width: 694`, `pixel_height: 599` (landscape)
- **THEN** corpus validation rejects: landscape fill-axis 694 < 1080 required

#### Scenario: Image meets floor but below long-edge preference

- **WHEN** an image records `pixel_width: 1300`, `pixel_height: 1600` (portrait)
- **THEN** corpus validation accepts the item; audit flags long edge 1600 < 1800 preferred

### Requirement: Panel fidelity

The device is a 3-bit (8-shade) greyscale panel and cannot encode hue. Every image item SHALL declare how its visual language survives reduction to pure luminance:

- **`native`** — the work was conceived under a pure-value constraint and has full fidelity on the panel. Includes etching, engraving, wood-engraving, pen-and-ink drawing, charcoal, silverpoint, ink-wash (sumi-e), monochrome lithograph, and black-and-white photography.
- **`robust`** — the work is color-origin but its value (tonal) structure carries the composition without hue. A tonally strong painting, a snow or night ukiyo-e where form is read by line and value rather than by colored field, a Vermeer interior, a late Rembrandt painting. Approved by the operator at list-review time; not assumed from `form` alone.
- **`color-dependent`** — figure/ground, focal point, or emotional register is carried by hue or saturation and collapses under desaturation. Iso-luminant color fields, pure-hue compositions (e.g., Red Fuji), Matisse color paintings, Rothko, Warhol colored work, Hopper's color-temperature paintings. These items SHALL NOT enter the corpus.

Corpus validation SHALL reject any image item with `panel_fidelity: color-dependent`. Ingestion SHALL refuse to fetch a list entry flagged `color-dependent` and SHALL record the refusal in the batch report so the operator can drop or replace the entry at list-review time, not at fetch.

The classification SHALL be proposed by `corpus propose-list` alongside tags, reviewed by the operator at list-approval time, and written into the sidecar at fetch. It is a curatorial judgment, not a mechanical derivation; the `form` vocabulary constrains but does not determine it.

#### Scenario: Color-dependent item in the list

- **WHEN** a list entry declares `panel_fidelity: color-dependent` and the operator runs `corpus fetch-list`
- **THEN** the tool skips the entry, records "refused: color-dependent on 3-bit greyscale panel" in the batch report, and does not write a sidecar

#### Scenario: Color-dependent item on disk

- **WHEN** a sidecar under `corpus/images/` declares `panel_fidelity: color-dependent`
- **THEN** corpus validation rejects the item and names it for removal

#### Scenario: Robust color-origin painting

- **WHEN** a sidecar for a Hiroshige snow scene declares `form: woodblock`, `panel_fidelity: robust`
- **THEN** corpus validation accepts the item; the triplet-authoring flow MAY use it as a visual-day hero

### Requirement: Rights tiers and their obligations

Each rights tier SHALL carry explicit obligations:

- `public_domain`: work is verifiably in the public domain worldwide or in the EU; `source_url` SHALL resolve to an authoritative record.
- `cc0`: work is released under Creative Commons Zero; `source_url` SHALL resolve to the CC0 declaration.
- `personal_library`: work is under copyright and admitted for private, non-commercial display on the operator's own device under the EU private-copy exception (Romania Law 8/1996 Art. 34). Acquisition SHALL be by fetching a publicly visible reproduction from a third-party source (museum / artist / archive page, literary site, publisher preview) or by typed text entry for short passages. There is no scanning path — when a reject item cannot be web-fetched at acceptable quality, the curatorial response is to substitute a comparable work or drop the item. The item SHALL carry `citation` with a bibliographic reference to a canonical published source for the work (e.g., `"Brumaru, *Julien Ospitalierul*, Humanitas, 2009"`), SHALL NOT be distributed beyond the operator's household, SHALL NOT be committed to git (neither binary nor text body; see "Binary storage policy" below), and SHALL NOT be uploaded to backup locations that leave the operator's control.

#### Scenario: Personal-library item in a PD folder

- **WHEN** a sidecar under `corpus/images/` declares `rights_tier: personal_library`
- **THEN** corpus validation rejects the item with an error directing it to `corpus/personal_library/`

#### Scenario: Personal-library binary in git staging

- **WHEN** a binary under `corpus/personal_library/` is added to the git index
- **THEN** the pre-commit check rejects the staging and names the offending file

### Requirement: Binary storage policy

Sidecars SHALL be git-tracked (metadata and inline text bodies). The following content bodies SHALL be git-ignored via root `.gitignore` and covered by the manifest:

- Image binaries under `corpus/images/`, `corpus/nocturne/`, and `corpus/personal_library/`.
- Optional text body files (`<id>.body.<lang>.txt`), if used as an operational convenience for very long texts.

The corpus SHALL remain reconstructible from git plus external backup by maintaining `corpus/_manifest.json` with the following entry per content body:

- `path` — corpus-relative file path
- `sha256` — hex-encoded digest of the binary content
- `bytes` — integer file size
- `mime` — MIME type
- `backup_uri` — location where the binary can be retrieved from external backup; format defined by `add-corpus-ingestion`

The manifest SHALL be regenerated whenever binaries are added, replaced, or removed.

#### Scenario: Manifest out of sync with filesystem

- **WHEN** a binary exists on disk but has no corresponding entry in `_manifest.json`, or vice versa
- **THEN** corpus validation reports the discrepancy and names every affected path

#### Scenario: Fresh clone restoration

- **WHEN** a fresh clone of the repository is made and binaries are absent, then a restore is run against `_manifest.json` with access to the external backup
- **THEN** every binary referenced by the manifest is present on disk with a matching sha256 after the restore completes

### Requirement: Stable identifiers

Item `id` values SHALL be stable for the lifetime of the corpus. Renaming an item's file basename SHALL be treated as removal of the old item and addition of a new item, and SHALL be recorded in the corpus change log.

#### Scenario: Renamed file

- **WHEN** `corpus/texts/basho-old-pond.yaml` is renamed to `corpus/texts/basho-frog-pond.yaml`
- **THEN** corpus validation treats this as a removal of `basho-old-pond` and an addition of `basho-frog-pond`, and references to the old id in pairings must be migrated explicitly

