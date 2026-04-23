# corpus-taxonomy Specification

## Purpose
TBD - created by archiving change add-corpus-schema. Update Purpose after archive.
## Requirements
### Requirement: Taxonomy files location and format

Controlled vocabularies SHALL live at `corpus/_taxonomy/` as YAML files, one per dimension:

- `corpus/_taxonomy/themes.yaml`
- `corpus/_taxonomy/mood.yaml`
- `corpus/_taxonomy/register.yaml`
- `corpus/_taxonomy/form.yaml`

Each file SHALL be a YAML mapping where keys are the canonical tag identifiers (kebab-case, lowercase) and values are objects with at least `label` (human-readable) and `description` (one-sentence gloss). The mapping keys SHALL be the strings referenced by sidecars.

#### Scenario: Sidecar referencing a taxonomy key

- **WHEN** a sidecar lists `mood: [contemplative]` and `corpus/_taxonomy/mood.yaml` contains a top-level key `contemplative`
- **THEN** validation accepts the reference

#### Scenario: Sidecar references a label instead of a key

- **WHEN** a sidecar lists `mood: ["Contemplative"]` (human-readable label) but the taxonomy key is `contemplative`
- **THEN** validation rejects the reference with a hint showing the canonical key

### Requirement: Theme vocabulary

`themes.yaml` SHALL contain exactly the following 37 entries, grouped conceptually (grouping is documentation only and does not appear in the file). The ratified vocabulary was canonicalized during `build-seed-corpus` from scene-type categories that survive on the 3-bit greyscale panel and match how real items cluster, replacing the original abstract-category starting set.

**Register** (what kind of daily the item suggests): `solitude`, `tender-companionship`, `ritual-and-gathering`, `everyday-life`, `childhood-and-play`, `attention-and-listening`, `reading-and-study`, `craft-and-play`, `work-making`

**Time and pace**: `morning`, `seasons-and-time`, `winter-and-ice`, `night-and-lamplight`, `decay-and-memory`, `mortality`

**Place and setting**: `urban`, `interior-and-domestic`, `architecture-and-structure`, `rural-pastoral`, `mountain-and-forest`, `sea-and-sky`, `water-and-reflection`, `garden-and-grove`, `paris-amsterdam-vintage`, `japan`

**Motion, weather, orientation**: `journey`, `travel`, `weather-facing`, `motion-and-gesture`, `light-shadow`

**Subject, body, image**: `portrait-and-face`, `body-and-figure`, `reflection-and-mirror`, `still-life`, `food-and-gathering`, `animals`, `machines-and-mechanisms`

#### Scenario: Day selects a theme

- **WHEN** the pairing pipeline reads the day's theme `solitude`
- **THEN** the theme is present as a top-level key in `themes.yaml` and the pipeline can proceed

### Requirement: Mood vocabulary (controlled)

`mood.yaml` SHALL contain exactly the following 45 entries and SHALL NOT accept additions or removals except through the amendment procedure (see "Vocabulary amendments"). The ratified set was canonicalized during `build-seed-corpus` from the moods real items actually need to express, refining the original 25-term starting set.

`contemplative`, `serene`, `quiet`, `still`, `melancholic`, `wistful`, `stoic`, `tender`, `intimate`, `warm`, `playful`, `wry`, `ironic`, `deadpan`, `absurd`, `surreal`, `uncanny`, `mysterious`, `atmospheric`, `haunting`, `stark`, `austere`, `grave`, `grim`, `tense`, `urgent`, `kinetic`, `dynamic`, `grand`, `awestruck`, `ecstatic`, `luminous`, `dim`, `ornate`, `sharp`, `alert`, `attentive`, `poised`, `self-possessed`, `enigmatic`, `unflinching`, `raw`, `documentary`, `romantic`, `unhurried`

#### Scenario: Ingestion proposes an unknown mood

- **WHEN** the ingestion tool attempts to write a sidecar with `mood: [meditative]` and `meditative` is not in `mood.yaml`
- **THEN** ingestion halts with an error naming the missing term and prompts for either (a) mapping to an existing term or (b) an amendment proposal

### Requirement: Register vocabulary (controlled)

`register.yaml` SHALL contain exactly the following 24 entries and SHALL NOT accept additions or removals except through the amendment procedure. The ratified set was canonicalized during `build-seed-corpus` from the voices real items speak in, refining the original 15-term starting set.

`lyric`, `aphoristic`, `classical`, `formal`, `iconic`, `intimate`, `tender`, `atmospheric`, `confessional`, `unadorned`, `documentary`, `reportorial`, `wry`, `sly`, `deadpan-absurd`, `absurdist`, `ornate`, `baroque`, `oracular`, `solemn`, `surreal`, `tender-bitten`, `quiet-sovereign`, `expressive`

Some terms appear in both `mood.yaml` and `register.yaml` (for example `tender`, `intimate`, `wry`, `ornate`, `atmospheric`, `surreal`, `documentary`). This is permitted: mood and register are orthogonal dimensions, and a term may legitimately describe both the affective key and the voice. Sidecars choose per-dimension independently.

#### Scenario: Sidecar with multiple registers

- **WHEN** an item is tagged `register: [solemn, oracular]`
- **THEN** both are present in `register.yaml` and validation accepts the item

### Requirement: Form vocabulary

`form.yaml` SHALL contain two disjoint groups:

**Text forms**: `haiku`, `tanka`, `sonnet`, `free-verse`, `stanzaic`, `fragment`, `aphorism`, `prose-poem`, `quote`, `song-chorus`, `lyric`

**Anchor-eligible text forms** — the subset usable as a triplet's hidden theme anchor (see `corpus-triplets` capability): `haiku`, `aphorism`, `fragment`, `quote`, `song-chorus`, `lyric`. Long forms (`tanka`, `sonnet`, `free-verse`, `stanzaic`, `prose-poem`) are not anchor-eligible.

**Image forms**: `etching`, `engraving`, `woodblock`, `wood-engraving`, `lithograph`, `drawing`, `photograph`, `painting`, `ink-wash`, `silverpoint`, `poster`

`wood-engraving` is the fine-line end-grain relief print (Ward, Baskin, Landacre, Gill) — always monochrome — and is kept distinct from `woodblock` (plank-grain relief, typically colored ukiyo-e and similar). `poster` covers graphic posters (Cassandre, Lautrec) that are lithographic or screenprint in production but read as a distinct image form curatorially.

The `form` field in each sidecar SHALL belong to the group matching the item's location in the filesystem: text forms for items under `corpus/texts/`, image forms for items under `corpus/images/`, `corpus/nocturne/`, and `corpus/personal_library/`.

#### Scenario: Image item with text form

- **WHEN** a sidecar under `corpus/images/` declares `form: haiku`
- **THEN** validation rejects the item with an error stating that `haiku` is a text form

### Requirement: Vocabulary amendments

A term SHALL be added to `mood.yaml` or `register.yaml` only through a documented amendment:

1. A change proposal identifies the need and lists existing items that the new term would retroactively apply to.
2. The term is added to the taxonomy file with `label`, `description`, and `added_in` (the change name).
3. Affected existing items are re-tagged in the same change.

Terms SHALL NOT be removed from `mood.yaml` or `register.yaml`; deprecated terms SHALL be kept with `deprecated: true` and `replaced_by` pointing to the canonical term. All items referencing a deprecated term SHALL be migrated within the same change.

#### Scenario: Adding a new mood term mid-project

- **WHEN** a change proposes adding `mood: reverent` and retags seven existing items
- **THEN** the taxonomy file gains the `reverent` entry with `added_in` naming that change, and the seven sidecars are updated in the same commit

#### Scenario: Term deprecation

- **WHEN** a change deprecates `mood: languid` in favor of `mood: unhurried`
- **THEN** `languid` remains in `mood.yaml` marked `deprecated: true` with `replaced_by: unhurried`, and all prior sidecars referencing `languid` are migrated to `unhurried` in the same change

### Requirement: Vocabulary stability gate

Before `build-seed-corpus` archives, the mood and register vocabularies SHALL have been unchanged across at least two consecutive ingestion batches. This gate does not apply to other changes that add vocabulary deliberately.

#### Scenario: Stability gate met

- **WHEN** two consecutive ingestion batches complete without amending `mood.yaml` or `register.yaml`
- **THEN** the vocabulary stability gate is satisfied and `build-seed-corpus` is eligible to archive

