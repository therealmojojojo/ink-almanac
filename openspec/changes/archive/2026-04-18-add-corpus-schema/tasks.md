## 1. Repository scaffolding

- [x] 1.1 Create root `.gitignore` with rules for `corpus/images/`, `corpus/nocturne/`, `corpus/personal_library/` binaries (jpg/jpeg/png/tif/tiff/webp), plus standard Node/Python/macOS entries
- [x] 1.2 Create `CLAUDE.md` at repo root documenting architecture, runtime topology, conventions, and the "requirements/ is reference-only" rule
- [x] 1.3 Create `README.md` with a short project description and pointer to `openspec/` and `CLAUDE.md`

## 2. Corpus filesystem

- [x] 2.1 Create empty directories: `corpus/images/`, `corpus/texts/`, `corpus/nocturne/`, `corpus/personal_library/`, `corpus/_taxonomy/`
- [~] 2.2 Add `.gitkeep` to each empty corpus directory so they exist in git  <!-- N/A: directories are populated with content -->
- [x] 2.3 Create `corpus/_manifest.json` (populated, schema_version:1 with entries[]) + `corpus/_manifest.README.md` describing the schema

## 3. Taxonomy files

- [x] 3.1 Write `corpus/_taxonomy/themes.yaml`
- [x] 3.2 Write `corpus/_taxonomy/mood.yaml`
- [x] 3.3 Write `corpus/_taxonomy/register.yaml`
- [x] 3.4 Write `corpus/_taxonomy/form.yaml`

## 4. Documentation

- [x] 4.1 Write `corpus/README.md` explaining the folder layout, the tier distinctions, and how to add a new item
- [x] 4.2 Document the rights-tier obligations in `corpus/README.md`, especially the personal-library tier's citation requirement and non-distribution constraint
- [x] 4.3 Document the vocabulary-amendment procedure in `corpus/_taxonomy/README.md` — when to add a term, when to deprecate, how to migrate affected items

## 5. Example sidecars

- [x] 5.1 Add `corpus/images/EXAMPLE.yaml.template` with annotated fields incl. `pixel_width`/`pixel_height` (orientation-aware floor) and `panel_fidelity` (3-bit greyscale constraint)
- [x] 5.2 Add `corpus/texts/EXAMPLE.yaml.template` single-language
- [x] 5.3 Add `corpus/texts/EXAMPLE-BILINGUAL.yaml.template` with `text_variants`
- [x] 5.4 Add `corpus/personal_library/EXAMPLE.yaml.template` with `citation`

## 6. Validation rules (documentation only)

- [x] 6.1 Write `corpus/_taxonomy/validation.md` enumerating every validation rule with exact error messages (contract for `add-corpus-ingestion`)

## 7. Cross-reference and verify

- [x] 7.1 Verify every field mentioned in `specs/corpus-schema/spec.md` appears in at least one EXAMPLE sidecar template (image/text/bilingual/personal-library templates together cover id, title, display_title, artist, author, year, rights_tier, source, source_url, citation, form, medium, pixel_width, pixel_height, panel_fidelity, panel_verdict, verdict_reason, verdict_reviewed_at, text, text_variants, language, themes, mood, register, added)
- [x] 7.2 Verify every theme, mood, register, and form term mentioned in `specs/corpus-taxonomy/spec.md` is present in the corresponding taxonomy YAML file (spot-checked: all 33 themes, 25 moods, 15 registers, and all text/image forms present; `form.yaml` additionally has `wood-engraving` and `poster` added via the native-B&W pivot, consistent with sidecars in use)
- [x] 7.3 Run `openspec validate add-corpus-schema` and resolve any findings  <!-- 2026-04-18: two `must contain SHALL or MUST` findings in corpus-triplets/spec.md ("Item reuse across triplets", "Anchor items stored as regular corpus items") — rewrote both to use SHALL/MUST explicitly. `openspec validate add-corpus-schema` now passes. -->
- [x] 7.4 Update `requirements/Requirements.md` with deprecation banner (done as a 2026-04-14 Note near top; reword as a one-line "Reference only. Superseded by openspec/specs/." if stricter match required)
