## Why

The corpus exists, the renderer exists, the faces are ratified — but nothing connects "today" to "what should Summary, Gallery, and Night show today." The pairing pipeline is that connection: it produces a dated JSON file (`pairings/{date}.json`) each morning declaring the active triplet and the Night nocturne for that day, which the renderer reads at render time.

The architecture is substantially simpler than originally planned. The ratification of `corpus-triplets` moved the curatorial work out of runtime retrieval and into authored triplet files. The pipeline's job is no longer "find two items whose tags intersect" — it is "pick a triplet from the eligible pool." All the taste is upstream in the triplet files; the pipeline only does scheduling and recency-spacing.

The pipeline is pre-generated in weekly batches rather than called live each morning. Live daily generation introduces operational fragility for a feature where latency doesn't matter. Weekly batches produce 7 days at a time, take a fraction of a second, are auditable before they fire, and let the operator pre-generate months of content.

## What Changes

- Introduce a Python module under `pairing/` implementing **triplet selection**: given a date, pick the next triplet from the eligible pool (triplets not shown in the recency window, matching the day's flavor target, optionally respecting seasonal theme hints).
- Introduce a **flavor cadence**: a YAML config at `pairing/config/flavor_cadence.yaml` declaring the target ratio of visual-day to text-day triplets across the week/month (default ~60/40).
- Introduce a **seasonal theme hints** config at `pairing/config/seasonal_hints.yaml` — a per-season soft bias toward triplets whose `themes` align with the season. This is a re-ranking hint, not a hard filter — triplets without season alignment remain eligible.
- Introduce the **weekly pre-generation job**: runs Sunday night (23:30 local time), produces the next 7 days of pairings as `pairings/{iso-date}.json`, one file per day.
- Introduce a **year-ahead buffer mode**: a CLI command that can pre-generate an entire year's pairings on demand. Useful for hands-off operation.
- Introduce the **recency store**: a small JSON index of used triplet ids and used nocturne ids by date, consulted during selection to filter out triplets used in the past N days (default 180; enough to avoid near-repeats, loose enough to not exhaust a small triplet pool).
- Introduce **Night-face selection**: for each date, resolve the Night image as either (a) the active triplet's `aligned_nocturne` if set, or (b) a sample from the general nocturne pool that has not appeared in the recency window.
- Introduce **idempotency and regeneration**: running the pipeline for a date that already has a pairing file is a no-op unless `--force` is passed. The operator can review pre-generated pairings and regenerate specific days if desired.
- Introduce a **batch report**: each pipeline run produces a small report summarizing which triplets fired, flavor-cadence adherence, how full the eligible pool was, seasonal-hint hits, any fallbacks triggered.

## Capabilities

### New Capabilities

- `pairing-pipeline`: The algorithm and scheduling that selects each day's active triplet and Night nocturne from the corpus, writes `pairings/{date}.json` files, and maintains the recency store.

### Modified Capabilities

None. The pairing pipeline consumes `corpus-schema`, `corpus-taxonomy`, `corpus-triplets`, and eventually the `add-rendering-pipeline` output. It does not modify ratified specs here.

## Impact

- **New Python module** under `pairing/src/inkplate/pipeline/` with a CLI subcommand `corpus pair` for running and inspecting pairings.
- **New config files**: `pairing/config/flavor_cadence.yaml`, `pairing/config/seasonal_hints.yaml`, `pairing/config/recency.yaml`.
- **New state directory**: `pairings/` at the repo root, containing one JSON file per date. Gitignored — generated content, not source.
- **New state file**: `pairings/_recency.json` tracking used-triplet and used-nocturne history for recency-spacing. Gitignored.
- **New HA automation** (defined in `add-ha-integrations`): triggers the weekly pre-generation at the scheduled time.
- **Collapses previously-planned complexity**: no more theme-calendar monthly rotation, no more mood/register intersection retrieval, no more hero/companion shortlists. All replaced by triplet selection. The original `experiment-pairing-viability` change becomes trivially satisfied — the "can pairing work?" question no longer depends on tag-overlap retrieval succeeding; it depends only on whether triplets can be authored and selected, which they plainly can.
- **Dependency on corpus**: the pipeline requires an initial pool of committed triplets under `corpus/_triplets/` to operate. Before `build-seed-corpus` completes its triplet phase, the pipeline can run in dry-mode only.
