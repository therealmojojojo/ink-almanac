## Context

The Inkplate dashboard's Gallery and Summary modes are driven by a curated pool of images and texts. Subsequent changes — ingestion, pairing, rendering — all consume this pool through a structured contract. The original `requirements/Requirements.md` sketched YAML examples but did not define the schema normatively, did not enumerate a controlled vocabulary, and did not address binary storage. Without a ratified contract, every downstream change would re-invent its assumptions and drift.

This design codifies that contract before any code exists, so the team (operator + Claude) can build ingestion, embeddings-or-not decisions, pairing retrieval, and rendering against a single source of truth.

## Goals / Non-Goals

**Goals:**
- A sidecar schema rich enough to drive tag-based retrieval (theme + mood + register) and per-form typography routing, without introducing free-text tag drift.
- Controlled vocabularies (mood, register, form) that stay small, auditable, and amendable only through explicit changes.
- A binary-storage policy that keeps the repo lightweight and text-only while remaining reconstructible from external backup.
- Legal clarity on the personal-library tier, encoded in the tier taxonomy and validation rules.

**Non-Goals:**
- Implementing ingestion pipelines, source connectors, or the Claude-assisted tagging CLI. Those belong to `add-corpus-ingestion`.
- Populating the taxonomy labels/descriptions beyond starter content. The `build-seed-corpus` change refines them as real items push against the vocabulary.
- Defining the pairing query language, retrieval algorithm, or theme calendar. Those belong to `add-pairing-pipeline`.
- Embedding generation. The current architecture is tag-only; embeddings may be revisited as an optional corpus-management tool later.

## Decisions

### Two capabilities, not one

The proposal splits this into `corpus-schema` (structure) and `corpus-taxonomy` (vocabularies). Rationale: structure changes rarely (field additions, tier additions), vocabulary evolves continuously during `build-seed-corpus`. Splitting isolates amendments — a new mood term doesn't force reviewing filesystem layout requirements.

Alternative considered: single `corpus` capability. Rejected because vocabulary changes would blur git diff boundaries and make the amendment procedure less cleanly enforceable.

### Sidecar YAML over JSON

YAML for human-editable sidecars; JSON for the binary manifest (machine-generated, machine-validated). YAML is kinder for multi-line text content (poems embedded directly) and anchors/aliases if we ever need them. JSON's stricter grammar is preferable for the manifest's checksum integrity.

### Controlled vocabularies enforced at ingestion, not at runtime

Sidecars reference vocabulary keys by value, not by pointer. Validation is a pre-ingestion gate; the renderer and pairing pipeline trust sidecars at runtime. Rationale: runtime validation would couple every consumer to the taxonomy parser; ingestion-time validation makes the taxonomy a build-time invariant.

### Taxonomy format: mapping with `label` + `description`, not flat list

`themes.yaml: { solitude: { label: "Solitude", description: "..." } }` rather than `themes: [solitude, morning, ...]`. The richer form lets the ingestion UI present readable labels, supports future additions (e.g. `seasonal_boost` hints) without schema churn, and makes deprecation (`deprecated: true`, `replaced_by: ...`) natural.

### Stable ids, rename = removal + addition

Corpus ids are contracts between the corpus and downstream pairings. Allowing in-place renames would silently break historical pairings-by-id references. Treating rename as a pair of operations forces an explicit migration decision.

### Binaries gitignored + manifest-based restore

Alternatives: Git LFS (Option A), commit binaries plain (Option C). Rejected because:
- LFS has a billing cliff and forces every clone through `git lfs install`; it also complicates the personal-library tier's legal posture (LFS-stored binaries feel closer to "distribution" than a local-only backup).
- Plain commits scale poorly and bloat history.

The manifest-plus-restore approach keeps the repo pure-text forever, aligns personal-library with its private-copy legal basis (binaries never leave the operator's control), and matches the "you restore from backup like a music library" mental model.

Implementation of the restore script and backup format is deferred to `add-corpus-ingestion`. The schema here commits only to the manifest's shape and invariants.

### Personal-library tier as a first-class rights tier, not a flag

Alternative: treat it as `rights_tier: copyrighted` with a `private_copy: true` flag. Rejected because the personal-library tier is distinguished by legal obligations (citation required, not in git, never distributed), not just "copyrighted with a flag." Making it a distinct tier enforces the obligations through validation rather than hoping flags are respected.

### Personal-library covers any acquisition channel, not just book scans

The tier was originally drafted imagining scans from physically owned books. In practice, the operator's favorite 20th-century poets and photographers are reproduced widely on the open web by reputable third parties (museum sites, artist estates, literary archives, publisher previews), and the EU private-copy exception does not turn on acquisition channel — it turns on the private, non-commercial nature of the use. The tier's obligations (citation to a canonical published source, never distributed, never committed to git, never backed up to locations outside operator control) attach identically whether the item came from a phone scan of a book or a web download of a museum's own reproduction.

Rationale: gating the tier on book-scanning would make roughly half of the operator's taste (Brumaru, Dinescu, Cartier-Bresson, Doisneau, Iancu, Warhol, Hopper) effectively unreachable without a scanning project that isn't the point of the device. Keeping the obligations strict while broadening acquisition matches both the legal posture and the project's lightweight-curation premise.

### Personal-library text bodies stored in git-ignored sibling files

For `rights_tier: public_domain` and `cc0` text items, the verbatim text lives inline in the YAML sidecar (`text` or `text_variants`). For `rights_tier: personal_library` text items, the text body SHALL NOT appear in the sidecar. Instead, each language variant of the text lives in a sibling file `<id>.body.<lang>.txt` under `corpus/personal_library/`, and those files are git-ignored exactly like image binaries (covered by the manifest for restore).

Rationale: sidecars are git-tracked. Inlining a Brumaru quatrain into a sidecar would commit the copyrighted text to the repository's history, where it would persist indefinitely and be vulnerable to accidental publication (repo becoming public, clones shared, etc.). Keeping the body in a git-ignored sibling file makes the metadata Git-safe while keeping the content body on the same private-copy footing as images. Restore still works because the manifest covers body files the same way it covers binaries.

Alternative considered: mark the sidecar itself as git-ignored when `rights_tier: personal_library`. Rejected because then downstream consumers (pairing pipeline, renderer) would have no tracked record of the item's metadata on a fresh clone; operators would discover the gap only at runtime. Splitting body from metadata keeps the metadata visible in git while the body stays outside it.

### Themes are 33 entries, fixed at this change

The 33-theme list was agreed in design conversation. It is deliberately pre-ratified here so ingestion can proceed with clear targets. Theme additions become rare events, through their own changes, with a rationale ("coverage gap in the `X` zone").

### Form vocabulary is split text/image and enforced by folder

Cross-type `form` values (a text tagged `etching`) are always errors and benefit from immediate rejection. Folder-based enforcement is cheap and matches how humans actually think about the corpus.

## Risks / Trade-offs

- **Vocabulary too small → tagging feels forced.** During `build-seed-corpus`, real items will push against the 25-mood / 15-register vocabulary. Mitigation: the amendment procedure allows controlled growth; the stability gate ensures amendments settle before archival.

- **Vocabulary too large → retrieval fragments.** If `mood.yaml` grows past ~40 terms, tag intersection for the companion pick starts missing matches because items share fewer tags. Mitigation: the amendment procedure requires justification; deprecation-with-migration folds near-synonyms back into canonical terms.

- **Binary restore is untested until `add-corpus-ingestion` lands.** A fresh clone has no binaries and no tooling to restore them until the next change ships. Mitigation: explicit acceptance in `add-corpus-ingestion`'s specs that restore must round-trip any committed manifest.

- **Personal-library compliance depends on operator discipline.** The gitignore check catches commits (including text body files now, not just images); it does not catch, e.g., manually uploading a `corpus/personal_library/` file to a public server, or configuring a backup scheme that pushes to a non-private location. Mitigation: documentation in `CLAUDE.md`, the tier's `rights_tier` validation text, and an ingestion-time rule (defined in `add-corpus-ingestion`) that personal-library content defaults to operator-controlled backup schemes only; the risk is fundamentally operational, not technical.

- **Stable-ids policy slows refactoring.** If the operator decides on a cleaner naming scheme later, bulk renames become expensive (every rename must be logged). Mitigation: invest early in id conventions; provide a migration helper in `add-corpus-ingestion`.

## Migration Plan

This is a greenfield capability — no migration from prior state. Ratification order:

1. This change archives. `corpus/_taxonomy/*.yaml` files exist with the agreed vocabularies and starter labels/descriptions.
2. `.gitignore` rules are in place.
3. `corpus/_manifest.json` exists as an empty object.
4. Downstream changes (`add-corpus-ingestion`, `build-seed-corpus`, `add-pairing-pipeline`, `add-rendering-pipeline`) can bind to these shapes.

Rollback is trivial — delete `corpus/` and `corpus/_taxonomy/` directories; no other code depends on them yet.

## Open Questions

1. **Should `themes.yaml` carry seasonal-modifier hints** (`autumn_boost: [decay, memory]`) or keep that in a separate config file? Leaning separate — taxonomy stays descriptive, the pairing pipeline owns scheduling logic. Deferred to `add-pairing-pipeline`.

2. **Handling multiple language variants in images** (a Caravaggio with Italian and English titles): the current schema assumes images are language-neutral. Probably fine in practice; revisit if Romanian-language caption needs arise.

3. **Versioning the taxonomy files.** Do we add a `schema_version` field inside each taxonomy file for forward compatibility? Deferred; add if/when the first backward-incompatible taxonomy change arises.
