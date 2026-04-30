## STATUS: archived as superseded

What shipped: triplet generation via
`pairing/corpus_build_triplets_v2.py` (1764 triplets, 4.8 years of
daily content) + daily publish via `pairing/publish_today.py` and
HA cron at 06:00.

What did NOT ship: the full proposed architecture (config files
under `pairing/config/`, week-ahead and year-ahead buffer commands,
seasonal-hint scoring, rolling-window flavor cadence, recency JSON
state). The simpler sequence-rotation approach in
`corpus_build_triplets_v2.py` covers daily selection at acceptable
quality without the proposal's calendar/buffer machinery.

Revisit if (a) the daily rotation needs explicit seasonal weighting
beyond what theme-matching already gives, or (b) operator wants
review-and-edit visibility for an upcoming week's selections. The
proposal's full design is preserved in this archived folder.

---

## 1. Package scaffolding

- [-] 1.1 Create `pairing/pipeline.py` (or `pairing/corpus_pair.py` to match the flat layout used by other corpus subcommands)
- [-] 1.2 Wire `corpus pair` dispatcher group in `inkplate_corpus_cli.py` — subcommands: `generate`, `generate-week`, `generate-year`, `calendar`, `report`
- [-] 1.3 Shared utilities for corpus + triplet loading (reuse the helpers already in `corpus_validate.py` / `corpus_audit.py`)
- [-] 1.4 Create `pairings/` directory (runtime state; git-ignored) and add it to `.gitignore` alongside `pairings/_reports/`, `pairings/_recency_triplets.json`, `pairings/_recency_nocturnes.json`

## 2. Config files

- [-] 2.1 `pairing/config/flavor_cadence.yaml` — `visual-day: 0.60`, `text-day: 0.40`, normalised at load
- [-] 2.2 `pairing/config/seasonal_hints.yaml` — four sections (winter / spring / summer / autumn), each a list of theme ids; hemisphere defaults to northern, operator-overridable
- [-] 2.3 `pairing/config/recency.yaml` — `triplet_days: 180`, `nocturne_days: 45`
- [-] 2.4 Config loader that (a) validates every theme id against `corpus/_taxonomy/themes.yaml`, (b) normalises the flavor cadence, (c) halts with a clear error on unknown theme or malformed value

## 3. Triplet selection algorithm

- [-] 3.1 Load triplet pool from `corpus/_triplets/` into a list of lightweight records (id, flavor, themes, aligned_nocturne)
- [-] 3.2 Compute target flavor for a date via rolling-window cadence tracker
- [-] 3.3 Filter eligible pool against `pairings/_recency_triplets.json` with configurable window
- [-] 3.4 Recency relaxation: halve window and retry when the eligible pool is empty; record the relaxation in rationale + batch report
- [-] 3.5 Score eligible triplets: `+1` for flavor match, `+0.5` per matching seasonal-hint theme (cap `+1.5`)
- [-] 3.6 Deterministic tie-breaking via a `(date, corpus-hash)`-seeded PRNG so the same inputs produce the same output across runs
- [-] 3.7 Selection unit tests covering: happy path, flavor-tie break, seasonal-hint lift, recency relaxation, empty-pool (fail cleanly with diagnostic)

## 4. Night-face resolution

- [-] 4.1 If the selected triplet has `aligned_nocturne`, use it directly (no pool consultation)
- [-] 4.2 Else sample from general nocturne pool (`corpus/nocturne/` + `corpus/personal_library/nocturne/`) excluding `pairings/_recency_nocturnes.json` entries inside the configured window
- [-] 4.3 Same halve-and-retry relaxation as triplets
- [-] 4.4 Guard: only `panel_fidelity ∈ {native, robust}` nocturnes are candidates (validator already ensures this, but guard defensively at selection time)

## 5. Recency stores

- [-] 5.1 Atomic read-modify-write of `pairings/_recency_triplets.json` and `pairings/_recency_nocturnes.json` (write to `.tmp`, fsync, rename)
- [-] 5.2 On `--force` regeneration of a specific date: roll back that date's old triplet and nocturne entries (scrub only if not referenced by another date), then run selection, then write new entries
- [-] 5.3 Unit tests: add, roll back, boundary-date exclusion (distance-from-target)

## 6. Pairing file writer

- [-] 6.1 Emit `pairings/{iso-date}.json` with every field defined in the spec's "Daily pairing output file" requirement
- [-] 6.2 Validate the file before finalising (all required fields; `triplet_id` resolves; `nocturne_id` resolves and is panel-fidelity-ok; `flavor` matches; `date` matches filename)
- [-] 6.3 Idempotency: skip existing files unless `--force`
- [-] 6.4 Atomic write (write to `.tmp`, rename)

## 7. CLI commands

- [-] 7.1 `corpus pair generate --date <d> [--force] [--dry-run] [--verbose]`
- [-] 7.2 `corpus pair generate-week [--start <d>] [--force] [--dry-run]` (default start: next Sunday)
- [-] 7.3 `corpus pair generate-year [--start <d>] [--force]`
- [-] 7.4 `corpus pair calendar [--from <d>] [--to <d>]` — compact table of existing pairings
- [-] 7.5 `corpus pair report [--run <run-id>]` — print latest or named batch report
- [-] 7.6 `--dry-run` runs selection + prints results without writing `pairings/` or touching recency stores
- [-] 7.7 `--verbose` prints eligible-pool sizes, score breakdowns, and tie events

## 8. Batch report

- [-] 8.1 Write `pairings/_reports/{run-id}.md` per invocation
- [-] 8.2 Per-day rows: date, triplet id, flavor (matched cadence?), nocturne id (aligned?), seasonal-hint themes applied, recency-relaxation note
- [-] 8.3 Summary: flavor mix achieved vs target, distinct triplets fired, mean uses per triplet, distinct nocturnes sampled, count of recency relaxations, count of aligned-vs-sampled nocturnes
- [-] 8.4 Coverage warnings: triplets that never fired across the run, themes that never appeared, nocturnes never sampled, flavor-cadence drift >±1 day

## 9. HA trigger contract

- [-] 9.1 Document the `corpus pair generate-week` command stability contract (exit code, stdout format, idempotency) in `pairing/docs/pairing-pipeline.md`
- [-] 9.2 Hand off to `add-ha-integrations` for the actual Sunday-23:30 automation wiring

## 10. Documentation

- [-] 10.1 Extend `pairing/README.md` with the `corpus pair ...` subcommands
- [-] 10.2 Write `pairing/docs/pairing-pipeline.md` — operator walkthrough: daily generation, weekly pre-generation, year-ahead buffer, reviewing pairings via `corpus pair calendar`, regeneration of specific dates
- [-] 10.3 Document the flavor cadence, seasonal hints, and recency configs with annotated examples

## 11. Integration

- [-] 11.1 End-to-end: generate 4 weeks against the current corpus (301 triplets, 32 nocturnes); validate every file
- [-] 11.2 Determinism: same date + same corpus hash → identical pairing (given identical recency state)
- [-] 11.3 Regeneration: force-regenerate one date mid-week; confirm that date's recency entries roll back correctly and neighbouring dates are untouched
- [-] 11.4 Thin-pool robustness: run year-ahead against a scratch copy of the corpus with half the triplets deleted; confirm the run completes with documented recency relaxations and coverage warnings
- [-] 11.5 Renderer hand-off: verify `add-rendering-pipeline` can consume `pairings/{date}.json` and produce correct Summary and Gallery faces from the referenced triplet + its anchor / summary / gallery items
