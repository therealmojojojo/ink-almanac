## Context

The pairing pipeline is the daily content choice — simple conceptually, small in scope. The design collapsed dramatically when `corpus-triplets` landed: every "how do we pair a hero and companion?" question (tag intersection, mood/register matching, theme calendar, shortlist fallbacks) moved upstream into authored triplet files. What's left for the pipeline is *scheduling*, not *retrieval*.

## Goals

- One scheduling decision per day, auditable after the fact.
- Weekly pre-generation, not live daily generation (latency doesn't matter, but fragility does).
- Deterministic for the same inputs (operator can re-run and see the same result).
- Simple enough that a wrong decision is an operator-visible bug, not an emergent property.

## Non-goals

- No content generation inside the pipeline. All content comes from `corpus/_triplets/` (curator-approved).
- No LLM calls in the hot path. Triplet selection is deterministic scoring + seeded tie-break.
- No hero/companion retrieval. Triplets are pre-paired; the pipeline picks one.
- No theme calendar / monthly shuffle. Triplets carry their own themes; the pipeline re-ranks via soft seasonal hints, nothing else.

## Key shape

1. **Read** the triplet pool from `corpus/_triplets/` at run time.
2. **Read** the recency stores (`pairings/_recency_triplets.json`, `pairings/_recency_nocturnes.json`).
3. **Compute** a target flavor from the cadence config (soft bias, not a filter).
4. **Score** each eligible triplet: `+1` for flavor match, `+0.5` per matching seasonal-hint theme (capped at `+1.5`).
5. **Pick** the highest-scoring triplet; deterministic seeded tie-break.
6. **Resolve** the Night image: triplet's `aligned_nocturne` if present, else sample from the general nocturne pool minus recency.
7. **Write** `pairings/{date}.json` and update both recency stores atomically.
8. **Emit** a batch report.

Total: ~300 lines of Python. A week of generation executes in milliseconds. A year in a fraction of a second.

## Decisions and rationale

### Triplet selection, not hero/companion retrieval

The tag-based retrieval architecture (pick theme → shortlist images → pick hero → intersect moods/registers on the other side → pick companion, with three levels of fallback) was the pre-triplet design. Retrieval-quality was the open question that motivated `experiment-pairing-viability`.

Now: curators author triplets explicitly. The pair "stands alone" invariant is enforced at authoring time, not at runtime. Selection becomes trivial, and the failure modes shrink to scheduling concerns only (does the pool have enough triplets to avoid obvious repetition? are seasonal hints having the intended effect?). `experiment-pairing-viability` is effectively answered by the fact that 301 triplets were authored and validate clean at the end of `build-seed-corpus`.

### Pre-generation, not live

Pre-generate weekly. No runtime service. Lower operational fragility, zero cost. Latency-irrelevant work should not live on the critical path.

### Soft scoring, not hard filtering

Flavor cadence and seasonal hints are scoring biases, not filters. A triplet whose themes don't match the season is still eligible — it just sits at a lower score than one that does. Filters exhaust small pools and force recency relaxation; soft scoring lets the pool breathe.

Exception: recency *is* a hard filter. Recency collisions are the one thing that would definitely annoy an operator.

### Two recency stores, different windows

Triplet recency: 180 days. Large enough to avoid near-repeats across a season. Small enough that a ~300-triplet pool is always serviceable.

Nocturne recency: 45 days. Nocturnes rotate nightly (much higher cadence than triplets, which rotate once per day), and the pool is ~32 items. A 45-day window gives every nocturne roughly one showing per ~6 weeks.

Both are operator-configurable.

### Deterministic tie-break

Ties get broken by a PRNG seeded from `(date, corpus-hash)`. Two runs with the same corpus state and recency state produce the same pairing. That's how `--dry-run` is useful: what the preview shows is what the write will produce.

### Idempotent writes

Generating an existing date is a no-op. `--force` to overwrite. This means the Sunday-night HA automation can fire defensively; and the operator can pre-generate a year and then selectively regenerate days they want to change without disturbing neighbours.

## Alternatives considered

- **LLM-picks-the-pairing.** Rejected: defeats the point of authoring triplets. Taste is already encoded in the triplet; a second layer of LLM taste would drift and be harder to audit.
- **Embeddings-based re-rank.** Rejected: tags already capture the axes the operator cares about; embeddings introduce opacity and a model dependency for no demonstrated gain.
- **Hash-based flavor assignment (no cadence window).** Rejected: simpler but produces ugly clusters (three text-days in a row). A rolling-window target with soft bias avoids clusters without forcing a calendar.
- **Single recency store covering triplets and nocturnes.** Rejected: the pools have different sizes and rotation cadences; one window wouldn't serve both well.

## Open questions (defer to implementation)

1. **Rolling window size for flavor cadence.** Proposed 7 days; could be 14 (smoother, less reactive). Lean 7; revisit after first year of operation.
2. **Seasonal-hint weight `+0.5`.** Tuned against first-year feedback; no principled derivation yet.
3. **Corpus-hash choice.** sha256 of `_triplets/` directory's sorted file list? Or the `_manifest.json` sha of triplet files? Pick the cheapest during implementation.
4. **Regeneration semantics for `generate-week --force`.** Does it regenerate all 7 days, or only days where selection would differ? Lean "all 7, same recency roll-back rules as per-date `--force`."

## Rollback

Delete `pairings/`, `pairings/_reports/`, `pairings/_recency_triplets.json`, `pairings/_recency_nocturnes.json`, and `pairing/config/*.yaml`. Remove the HA automation binding. Renderer falls back to a placeholder face when `pairings/{today}.json` is absent.

The corpus itself is untouched by a rollback.
