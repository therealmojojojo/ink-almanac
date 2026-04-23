# Corpus validation rules

Catalogue of every rule the validator enforces. This is the contract between `corpus-schema` / `corpus-taxonomy` (specs) and `corpus_validate.py` (implementation). When either changes, update this document in the same change.

Rules are grouped as **errors** (fail the run, exit code 1) and **warnings** (reported, do not fail). Error-message wording below matches what the validator emits.

---

## Sidecar: common fields

**E-COMMON-MISSING** — missing required field  
> `<path>: missing required field: <field>`

Fires when any of these is absent: `id`, `title`, `year`, `rights_tier`, `source`, `form`, `themes`, `mood`, `register`, `added`. `title` may be empty string for untitled works. `year` may be `null` for unknown provenance; everything else must be present.

**E-COMMON-ID-MISMATCH** — `id` does not match filename basename  
> `<path>: id '<id>' does not match filename basename '<basename>'`

**E-COMMON-ID-DUPLICATE** — the same `id` appears in more than one sidecar  
> `<path>: duplicate id '<id>' (also in <other-path>)`

**E-COMMON-RIGHTS-TIER-INVALID** — `rights_tier` is not one of `public_domain`, `cc0`, `personal_library`  
> `<path>: rights_tier '<value>' is not one of public_domain, cc0, personal_library`

**E-COMMON-TIER-FOLDER-MISMATCH** — tier disagrees with folder  
> `<path>: rights_tier '<tier>' is not permitted under '<folder>/' — move to '<expected-folder>/'`

Personal-library items must live under `corpus/personal_library/` (or `corpus/personal_library/nocturne/`). Public-domain and CC0 items must live under `corpus/images/`, `corpus/texts/`, `corpus/nocturne/`.

**E-COMMON-SOURCE-URL-REQUIRED** — `source_url` missing for PD/CC0 item  
> `<path>: rights_tier '<tier>' requires source_url`

**E-COMMON-CITATION-REQUIRED** — `citation` missing for personal-library item  
> `<path>: rights_tier 'personal_library' requires a citation (format: "<Author>, *<Book Title>*, <Publisher>, <Year>[, page <N>]")`

## Sidecar: taxonomy membership

**E-TAX-UNKNOWN-THEME / UNKNOWN-MOOD / UNKNOWN-REGISTER / UNKNOWN-FORM**  
> `<path>: <field> value '<value>' is not a key in corpus/_taxonomy/<file>.yaml`

Fires when a sidecar references a tag that is not a top-level key in the corresponding taxonomy file. Label-casing variants (e.g., `"Contemplative"` for key `contemplative`) are rejected with the canonical key in the hint.

**E-TAX-EMPTY-THEMES / EMPTY-MOOD / EMPTY-REGISTER**  
> `<path>: <field> must be a non-empty array`

**E-TAX-FORM-GROUP-MISMATCH** — text form under an image folder or vice versa  
> `<path>: form '<value>' is a <text|image> form but the item lives under '<folder>/'`

## Sidecar: image items

Applies to items under `corpus/images/`, `corpus/nocturne/`, `corpus/personal_library/` (and `personal_library/nocturne/`) when no `text` / `text_variants` field is present.

**E-IMG-MISSING-ARTIST / MEDIUM / PIXEL-WIDTH / PIXEL-HEIGHT / PANEL-FIDELITY**  
> `<path>: image item missing required field: <field>`

`artist` may be empty string for anonymous works.

**E-IMG-PANEL-FIDELITY-INVALID**  
> `<path>: panel_fidelity '<value>' is not one of native, robust, color-dependent`

**E-IMG-PANEL-FIDELITY-COLOR-DEPENDENT**  
> `<path>: panel_fidelity 'color-dependent' items are not permitted in the corpus`

**E-IMG-RESOLUTION-FLOOR** — fill-axis below floor  
> `<path>: landscape fill-axis <width> < 1080 (dims <w>x<h>)`  
> `<path>: portrait fill-axis <height> < 693 (dims <w>x<h>)`

Landscape (width > height) must have `pixel_width ≥ 1080`. Portrait or square (height ≥ width) must have `pixel_height ≥ 693`.

**W-IMG-LONG-EDGE-PREFERENCE** (warning)  
> `<path>: long edge <max> < 1800 preferred (dims <w>x<h>)`

**E-IMG-BINARY-MISSING** — sidecar references no on-disk binary  
> `<path>: no binary found with any of extensions .jpg .jpeg .png .tif .tiff .webp`

**E-IMG-PANEL-VERDICT-REJECT** — item is marked for exclusion  
> `<path>: panel_verdict=reject — <verdict_reason>`

`panel_verdict: reject` fails the run; the item must be fixed, dropped, or refetched. `flag` items emit a warning only.

## Sidecar: text items

Applies to items under `corpus/texts/` and text items under `corpus/personal_library/`.

**E-TEXT-MISSING-AUTHOR**  
> `<path>: text item missing required field: author`

**E-TEXT-MISSING-BODY**  
> `<path>: text item must declare one of: text, text_variants, body_files`

**E-TEXT-LANGUAGE-EMPTY**  
> `<path>: text item language must be a non-empty array of ISO 639-1 codes`

**E-TEXT-VARIANTS-LANGUAGE-DISAGREES**  
> `<path>: text_variants keys <...> do not match language <...>`

## Triplets (`corpus/_triplets/*.yaml`)

**E-TRIP-MISSING** — missing required field  
> `<triplet-path>: missing required field: <field>`

Required: `anchor`, `summary`, `gallery`, `flavor`, `note`, `themes`, `added`.

**E-TRIP-REF-UNRESOLVED** — slot references a nonexistent item  
> `<triplet-path>: slot '<slot>' references unknown item id '<id>'`

**E-TRIP-ANCHOR-INELIGIBLE** — anchor refers to an item whose `form` is not anchor-eligible  
> `<triplet-path>: anchor '<id>' has form '<form>' which is not anchor-eligible`

Anchor-eligible text forms: `haiku`, `aphorism`, `fragment`, `quote`, `song-chorus`, `lyric`.

**E-TRIP-FLAVOR-MISMATCH** — `flavor` disagrees with the gallery type  
> `<triplet-path>: flavor '<flavor>' expects gallery type '<expected>' but '<id>' is '<actual>'`

`visual-day` triplets take an image in `gallery`; `text-day` triplets take a text.

**E-TRIP-IMAGE-SLOT-FIDELITY** — image slot filled by a non-native/non-robust item  
> `<triplet-path>: slot '<slot>' image '<id>' has panel_fidelity '<value>' — only native or robust permitted`

**E-TRIP-DUPLICATE-SLOT** — same id appears in more than one slot of the same triplet.

**E-TRIP-UNKNOWN-THEME** — theme not in `themes.yaml`.

## Manifest (`_manifest.json`)

**E-MAN-ENTRY-WITHOUT-FILE** — manifest entry has no corresponding file  
> `<path>: manifest entry points to missing file`

**E-MAN-FILE-WITHOUT-ENTRY** — on-disk binary has no manifest entry  
> `<path>: on-disk binary has no manifest entry`

**E-MAN-SHA-MISMATCH** (only with `--full`) — computed sha256 disagrees with manifest  
> `<path>: sha256 mismatch (expected <manifest>, got <computed>)`

## Summary format

At end of run:
```
scanned <N> sidecars, <M> triplets, <K> items in pool

  errors:   <count>
  warnings: <count>
```

Followed by one line per issue. Exit code 0 if `errors == 0`, else 1.
