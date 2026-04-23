## ADDED Requirements

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

`themes.yaml` SHALL contain exactly the following 33 entries, grouped conceptually (grouping is documentation only and does not appear in the file):

**Register**: `contemplative`, `ironic`, `absurd`, `tender`, `stoic`, `ecstatic`, `grim`

**Time & pace**: `morning`, `evening`, `solitude`, `togetherness`

**Subject**: `still-life`, `urban`, `rural-pastoral`, `interior`, `body`, `weather-facing`, `animals`, `water`, `light-shadow`

**Traditions**: `eastern-wisdom`, `romanian-voice`, `great-photographers`, `old-masters`, `documentary-20c`

**Orientations**: `love-longing`, `mortality`, `work-making`, `home-belonging`, `journey`, `procession-ritual`, `machines-mechanisms`, `food-hunger`

#### Scenario: Day selects a theme

- **WHEN** the pairing pipeline reads the day's theme `solitude`
- **THEN** the theme is present as a top-level key in `themes.yaml` and the pipeline can proceed

### Requirement: Mood vocabulary (controlled, starting set)

`mood.yaml` SHALL start with the following entries and SHALL NOT accept additions except through an amendment procedure (see "Vocabulary amendments"):

`contemplative`, `kinetic`, `tender`, `ecstatic`, `grim`, `alert`, `languid`, `unhurried`, `urgent`, `attentive`, `ironic`, `deadpan`, `yearning`, `stoic`, `melancholy`, `ebullient`, `austere`, `lush`, `stark`, `luminous`, `dim`, `cold`, `warm`, `tense`, `serene`

#### Scenario: Ingestion proposes an unknown mood

- **WHEN** the ingestion tool attempts to write a sidecar with `mood: [meditative]` and `meditative` is not in `mood.yaml`
- **THEN** ingestion halts with an error naming the missing term and prompts for either (a) mapping to an existing term or (b) an amendment proposal

### Requirement: Register vocabulary (controlled, starting set)

`register.yaml` SHALL start with the following entries and SHALL NOT accept additions except through the amendment procedure:

`quiet-sovereign`, `deadpan-absurd`, `plainspoken`, `ornate`, `confessional`, `observational`, `oracular`, `tender-bitten`, `solemn`, `sly`, `unadorned`, `baroque`, `reportorial`, `lyric`, `aphoristic`

#### Scenario: Sidecar with multiple registers

- **WHEN** an item is tagged `register: [solemn, oracular]`
- **THEN** both are present in `register.yaml` and validation accepts the item

### Requirement: Form vocabulary

`form.yaml` SHALL contain two disjoint groups:

**Text forms**: `haiku`, `tanka`, `sonnet`, `free-verse`, `stanzaic`, `fragment`, `aphorism`, `prose-poem`, `quote`, `song-chorus`, `lyric`

**Anchor-eligible text forms** — the subset usable as a triplet's hidden theme anchor (see `corpus-triplets` capability): `haiku`, `aphorism`, `fragment`, `quote`, `song-chorus`, `lyric`. Long forms (`tanka`, `sonnet`, `free-verse`, `stanzaic`, `prose-poem`) are not anchor-eligible.

**Image forms**: `etching`, `engraving`, `woodblock`, `lithograph`, `drawing`, `photograph`, `painting`, `ink-wash`, `silverpoint`

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
