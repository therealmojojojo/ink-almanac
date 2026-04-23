## ADDED Requirements

### Requirement: Daily pairing output file

The pipeline SHALL produce, for each target date, a JSON file at `pairings/{iso-date}.json` containing:

- `date` — ISO date string (matches filename)
- `triplet_id` — id of a triplet from `corpus/_triplets/` selected for this date
- `flavor` — `visual-day` or `text-day`, copied from the selected triplet
- `anchor_id` — the triplet's anchor (anchor-eligible short-form text)
- `summary_id` — the triplet's summary slot
- `gallery_id` — the triplet's gallery slot
- `nocturne_id` — the Night-face image for this date, resolved per the "Night-face resolution" requirement below
- `seasonal_hint_applied` — list of theme ids that contributed seasonal re-rank weight for this date, or an empty list
- `rationale` — short human-readable note: the selection reason (flavor cadence step, seasonal hint effect, recency pressure, fallback used)
- `generated_at` — ISO timestamp

The pipeline SHALL NOT duplicate triplet content into the pairing file; it SHALL reference by id and let the renderer resolve. This keeps pairings a thin scheduling document, not a denormalised copy of the corpus.

#### Scenario: Generating one day

- **WHEN** the operator runs `corpus pair generate --date 2026-05-07`
- **THEN** `pairings/2026-05-07.json` exists with all required fields populated, `triplet_id` refers to a triplet file under `corpus/_triplets/`, `nocturne_id` refers to an image under `corpus/nocturne/` or `corpus/personal_library/nocturne/`, and the pipeline's own validation reports valid

### Requirement: Triplet selection algorithm

For each target date D, the pipeline SHALL:

1. Load the current triplet pool from `corpus/_triplets/`.
2. Determine the **target flavor** for D from the flavor-cadence configuration (see "Flavor cadence"). This is a hint, not a hard filter.
3. Compute the **eligible pool**: triplets NOT used in the recency window (see "Recency store"). If the eligible pool is empty after recency filtering, the pipeline SHALL relax the recency window (halve it; relax again if still empty) and note the relaxation in the rationale.
4. **Score** each eligible triplet:
   - `+1` if its `flavor` matches the target flavor.
   - `+season_hint_weight` if any of its `themes` appears in the seasonal-hints list for D's season (weight configurable; default `+0.5` per matching theme, capped at `+1.5`).
5. Pick the highest-scoring triplet. Ties broken by deterministic pseudo-random choice seeded by `(date, corpus-hash)` so that the same inputs always produce the same output.
6. Write the pairing file with the selected triplet's id, flavor, and slot ids; resolve `nocturne_id` per the Night-face rule.

This selection is intentionally simple: all the taste work is already in the authored triplets.

#### Scenario: Flavor-cadence match preferred

- **WHEN** the target flavor for D is `visual-day`, two triplets tie on seasonal-hint score, and one is `visual-day` and the other `text-day`
- **THEN** the `visual-day` triplet is selected and the rationale notes "flavor cadence: visual-day"

#### Scenario: Seasonal hint adds weight

- **WHEN** D falls in winter, the seasonal hints for winter include `winter-and-ice` and `interior-and-domestic`, and a triplet carries themes `[winter-and-ice, solitude]`
- **THEN** the triplet gets a `+0.5` boost, which combined with a flavor-match can lift it above a triplet with neither advantage

#### Scenario: Recency relaxation

- **WHEN** every triplet in the pool has been used inside the configured recency window
- **THEN** the window is halved and selection retries; the rationale notes "recency relaxed to <N> days" for the affected date; the batch report flags the event

### Requirement: Night-face resolution

For each date D, `nocturne_id` SHALL be resolved as follows:

1. If the selected triplet declares `aligned_nocturne`, use that id.
2. Otherwise, pick a sample from the general nocturne pool (`corpus/nocturne/` + `corpus/personal_library/nocturne/`) that is NOT in the nocturne-recency window for D.
3. If every nocturne is in the recency window, relax the window (same halve-and-retry approach as triplet recency) and note the relaxation.

The selected `nocturne_id` SHALL satisfy `panel_fidelity ∈ {native, robust}` per `corpus-schema`.

#### Scenario: Aligned nocturne wins

- **WHEN** the selected triplet for D has `aligned_nocturne: brassai-paris-de-nuit-steps`
- **THEN** `nocturne_id: brassai-paris-de-nuit-steps` is written into the pairing file without consulting the general nocturne pool

#### Scenario: General nocturne sampled

- **WHEN** the selected triplet has no `aligned_nocturne`
- **THEN** a nocturne id is sampled from the general pool, excluding ids used in nocturne recency for D, and written as `nocturne_id`

### Requirement: Flavor cadence

A YAML config at `pairing/config/flavor_cadence.yaml` SHALL declare the target ratio of `visual-day` to `text-day` across a window. Default: 60% visual / 40% text across every rolling 7-day window. The pipeline SHALL use the cadence to set the **target flavor** for each date, not to force it: selection remains a soft scoring bias, not a hard filter.

The file is operator-editable. The cadence SHALL sum to 1.0 (or be normalised at load time) and SHALL reference only `visual-day` and `text-day` (the flavors defined by `corpus-triplets`).

#### Scenario: Cadence across a week

- **WHEN** the cadence is 60/40 and the pipeline generates 7 consecutive days
- **THEN** across the 7 pairings, the observed flavor mix is within ±1 day of the cadence target (i.e., 3 or 4 text-day pairings; 4 or 5 visual-day pairings)

### Requirement: Seasonal hints

A YAML config at `pairing/config/seasonal_hints.yaml` SHALL map each season (`winter`, `spring`, `summer`, `autumn`) to a list of theme ids from `corpus/_taxonomy/themes.yaml` that the pipeline re-ranks toward for dates falling in that season. Season detection uses astronomical boundaries defaulting to the northern hemisphere; hemisphere is operator-configurable.

The hint is a soft re-rank, never a filter: triplets whose themes don't overlap with seasonal hints remain eligible and can still be selected.

Unknown theme ids in `seasonal_hints.yaml` SHALL halt load with an explicit error naming the offending term and the section it's in.

#### Scenario: Seasonal hint applied

- **WHEN** D is in winter, `seasonal_hints.yaml` lists `[winter-and-ice, interior-and-domestic, night-and-lamplight]` for winter, and a triplet carries `themes: [winter-and-ice]`
- **THEN** the triplet gets a seasonal-hint boost and the written pairing records `seasonal_hint_applied: [winter-and-ice]`

#### Scenario: Unknown theme in hints

- **WHEN** `seasonal_hints.yaml` contains `foo-theme` that is not in `themes.yaml`
- **THEN** the pipeline refuses to run and reports `unknown theme in seasonal_hints.yaml: foo-theme`

### Requirement: Recency store

The pipeline SHALL maintain two recency stores, atomically updated when a pairing is written:

- `pairings/_recency_triplets.json` — map of triplet id to most-recent use date
- `pairings/_recency_nocturnes.json` — map of nocturne image id to most-recent use date

Default recency windows (operator-configurable via `pairing/config/recency.yaml`):

- Triplet recency: **180 days**.
- Nocturne recency: **45 days** (smaller because the pool is smaller and nightly rotation is higher-cadence).

When a pairing is regenerated (`--force`), the old triplet and nocturne entries for that date SHALL be rolled back if no other date references them, then the new entries written.

#### Scenario: Triplet excluded by recency

- **WHEN** generating 2026-05-07 and triplet `stillness-of-sundays` was last used on 2026-03-01 (67 days back, inside the 180-day window)
- **THEN** the triplet is NOT in the eligible pool for 2026-05-07

#### Scenario: Nocturne eligible again

- **WHEN** generating 2026-05-07 and nocturne `brassai-lamp-post-fog` was last used on 2026-03-01 (67 days back, outside the 45-day nocturne window)
- **THEN** the nocturne is eligible for sampling

#### Scenario: Regeneration rolls back

- **WHEN** `pairings/2026-05-07.json` exists pointing at triplet A and nocturne B, and the operator runs `corpus pair generate --date 2026-05-07 --force`
- **THEN** A's recency entry for that date is cleared (if that was its only reference), B's nocturne-recency entry likewise, retrieval runs, the new triplet and nocturne are written, and their recency entries are added

### Requirement: Idempotent runs

Running the pipeline against a date whose `pairings/{date}.json` already exists SHALL be a no-op unless `--force` is passed. This lets the weekly pre-generation job run safely — and lets the operator regenerate specific days without touching others.

#### Scenario: Safe re-run

- **WHEN** `pairings/2026-05-07.json` exists and `corpus pair generate --date 2026-05-07` runs without `--force`
- **THEN** the existing file is left untouched and the tool reports "skipped: already exists"

### Requirement: Weekly pre-generation

A subcommand `corpus pair generate-week [--start <date>]` SHALL produce pairings for 7 consecutive days starting from the given date (default: next Sunday's date, i.e., if run on Sunday N, generates Monday N+1 through Sunday N+7). Each day is generated using the same algorithm; the recency stores are consulted continuously so the 7 pairings don't collide with each other or with historical runs.

#### Scenario: Sunday-night run

- **WHEN** Sunday 2026-05-03 at 23:30 local, the HA automation runs `corpus pair generate-week`
- **THEN** 7 JSON files are written for 2026-05-04 through 2026-05-10, each referencing a distinct eligible triplet, and the recency stores reflect all 7 new entries

### Requirement: Year-ahead generation

A subcommand `corpus pair generate-year [--start <date>]` SHALL produce pairings for 365 consecutive days. Intended for hands-off operation against a stable corpus.

If a date cannot be satisfied even after recency relaxation (triplet pool too small relative to 365 days), the pipeline SHALL still write a pairing — relaxed as necessary — and the batch report SHALL flag the affected dates and the corpus-size gap.

#### Scenario: Year-ahead run against a healthy corpus

- **WHEN** the operator runs `corpus pair generate-year --start 2026-05-01` against a corpus with 300+ triplets
- **THEN** 365 JSON files exist for 2026-05-01 through 2027-04-30, each with a valid pairing, and the batch report shows no thin-pool warnings

#### Scenario: Year-ahead with a thin pool

- **WHEN** the triplet pool is ~120 and a year has 365 days
- **THEN** recency relaxation fires on many dates; every pairing still writes; the batch report names the dates whose recency window was relaxed and recommends either growing the triplet pool or accepting more repetition

### Requirement: Batch report

Each invocation (single-date, weekly, or yearly) SHALL produce a report at `pairings/_reports/{run-id}.md` containing:

- Target dates and invocation command
- Per-day: selected triplet id, flavor (and whether it matched cadence), nocturne id (and whether aligned or sampled), seasonal-hint themes applied, recency-relaxation note if any
- Summary: flavor-mix achieved vs target, triplet-pool use count (how many distinct triplets fired, mean uses per triplet), nocturne-pool use count, count of recency relaxations, count of aligned vs sampled nocturnes
- Coverage warnings: triplets that have never fired, themes that never appeared, nocturnes never sampled, any flavor cadence drift >±1 day of target

#### Scenario: Weekly report

- **WHEN** a weekly run completes
- **THEN** a markdown report file is written with per-day detail and the summary sections, and the report path is printed at the end of the run

### Requirement: Validation of pairing files

Each written pairing file SHALL be validated before it is finalised:

- All required fields are present and well-typed.
- `triplet_id` refers to a file under `corpus/_triplets/`.
- `anchor_id` / `summary_id` / `gallery_id` match the selected triplet's slot assignments.
- `nocturne_id` resolves to an image under `corpus/nocturne/` or `corpus/personal_library/nocturne/` with `panel_fidelity ∈ {native, robust}`.
- `flavor` is one of `visual-day` / `text-day` and matches the selected triplet's flavor.
- `date` is a valid ISO date and matches the filename.

Validation failures SHALL halt the write, surface the offending rule, and exit non-zero.

#### Scenario: Referenced triplet missing

- **WHEN** selection picks triplet `stillness-of-sundays` but `corpus/_triplets/stillness-of-sundays.yaml` has been deleted between selection and write
- **THEN** validation fails, no pairing file is written, and the tool reports `triplet_id refers to non-existent triplet: stillness-of-sundays`

### Requirement: CLI surface

The pairing pipeline SHALL extend the existing `corpus` CLI with a `pair` command group:

- `corpus pair generate --date <iso-date> [--force] [--dry-run] [--verbose]`
- `corpus pair generate-week [--start <iso-date>] [--force] [--dry-run]`
- `corpus pair generate-year [--start <iso-date>] [--force]`
- `corpus pair calendar [--from <date>] [--to <date>]` — prints the existing pairings across a date range in a compact table for review
- `corpus pair report [--run <run-id>]` — prints the latest batch report (or a named one)

`--dry-run` SHALL run selection and print what would be written, without touching `pairings/` or the recency stores. `--verbose` SHALL print eligible-pool sizes, score breakdowns, and ties.

#### Scenario: Dry-run preview

- **WHEN** the operator runs `corpus pair generate-week --dry-run`
- **THEN** the tool prints 7 proposed pairings with their selection rationales, and no file is written under `pairings/` and no entry is added to any recency store

### Requirement: HA trigger contract

The pipeline SHALL expose a stable command and behavior contract that `add-ha-integrations` can bind a Sunday-23:30 automation to. Specifically:

- The command is `corpus pair generate-week` (no arguments; defaults to next Sunday's start).
- Exit code 0 on success (all 7 files written), non-zero on any write failure.
- On success, the tool prints the report path on stdout so HA can surface it in a notification.
- Idempotent: a second invocation for the same target window is a no-op.

Nothing in `add-pairing-pipeline` implements the HA trigger itself — only the contract the trigger binds to. The trigger lives in `add-ha-integrations`.

#### Scenario: HA binding surface

- **WHEN** a Home Assistant automation fires `corpus pair generate-week` at Sunday 23:30 and the command succeeds
- **THEN** exit code 0 is returned, stdout contains the batch-report path, and 7 pairing files + report are on disk
