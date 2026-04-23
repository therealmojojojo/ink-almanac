## Context

The previous two changes defined a schema and will build ingestion tooling. Neither produces a single sidecar. The seed change is where the operator, helped by Claude, sits down repeatedly and builds the corpus over time. It is not a software change — it is an operational commitment with gating criteria, audit structure, and milestone definitions.

The shape of this change is unusual for OpenSpec: no code ships, no module is introduced, nothing is wired together. Instead, targets and gates are ratified, canonical lists are authored and executed, and the change remains open for as long as it takes to hit final seed. This is deliberate. Treating corpus-building as a spec-governed change gives it the same accountability and traceability as any code change, while still respecting its human-paced nature.

## Goals / Non-Goals

**Goals:**
- Reach a corpus that carries the dashboard for at least a year without any theme exhausting its past-year-eligible pool.
- Let the vocabulary stabilize by confronting it with real items, not speculation.
- Produce an auditable record of what was ingested, when, why, and from where — crucially, the canonical list files themselves are committed, so the curatorial choices are legible.
- Make coverage imbalances visible and self-correcting through targeted subsequent lists.
- Keep the personal-library tier honest (legal obligations respected, tier routing correct).

**Non-Goals:**
- Prescribing a schedule. The operator decides when to run batches.
- Full automation. List approval and post-fetch pruning are intentionally operator-driven, even though per-item review is not.
- Corpus perfection. "Looks like ours" beats "covers every edge case."
- Vocabulary final form. Amendments happen; this change records them but does not own them.
- Coverage balance for its own sake. If a category's canon genuinely has 40 works and another has 10, the corpus reflects that — with a theme-level floor as a guardrail rather than a per-artist ceiling.

## Decisions

### Anthology-first assembly

Ingestion proceeds as a sequence of canonical-list batches, one per category. For each category (a poet's selected, a photographer's canon, a named print series, an anthology section), the operator runs `corpus propose-list` → edits the resulting YAML list file → runs `corpus fetch-list` against it → prunes via contact sheet. Approved list files are committed under `openspec/changes/build-seed-corpus/lists/<category>.yaml`.

Rationale: the corpus target is small (a few hundred items per side); every item should be drawn from the canon for its category. Working from named canonical lists makes taste decisions concentrated and reviewable, and produces a curatorial record that future-operator can read later to understand why certain items exist.

Alternative considered: theme-driven discovery batches ("find me more morning items"). Rejected because it centers the tooling's query language rather than the operator's taste; it also encourages items that match a theme tag without being canonically interesting.

### Two milestones, both gating

**Vocabulary stable** (two consecutive non-amending canonical-list batches) and **Final seed** (300+300, ≥15 applicable items per theme per side). Archiving requires both. Rationale:

- **Vocabulary stable** prevents premature archival with vocabulary still in flux — a post-archive amendment would be expensive because it would cascade through already-tagged items.
- **Final seed** ensures the past-year filter has enough room to operate for a year or more of normal use with the Spotify-radio rotation pattern.

Alternatives considered:
- Three milestones with a v1 intermediate at 300+300 before a final at 1000+1000. Rejected because the anthology-first approach reaches useful corpus depth at 300+300; bloating toward 1000+1000 would dilute the canon with second-tier inclusions.
- Size-only target with no vocabulary gate. Rejected because a locked taxonomy is the contract with downstream consumers; ratifying the seed with unstable vocabulary would force re-tagging cascades after archive.

### 300+300 is the final target, not a milestone en route

With Spotify-radio selection (70% core / 20% adjacent / 10% weird) and a daily rotation of ~2 items, 300+300 yields months of unique presentation before any repeat, and the canonical list mechanism means new lists can be authored post-archive if rotation ever stales. Scaling the target higher would trade canonical quality for filler; this corpus is deliberately small-and-excellent rather than large-and-representative.

### Per-theme applicability, not exclusivity

An item tagged `themes: [urban, solitude, morning]` counts toward all three themes' coverage, not just one. Rationale: the pairing pipeline queries by theme; a single item serves multiple themes. The coverage metric reflects retrieval reality, not tag exclusivity.

Subtle trade-off: this means a very general item (many themes) contributes more to coverage than a specific item. The ≥15/theme target implicitly accepts that some items are more load-bearing than others.

### No personal-library ceiling

The original draft capped personal-library at 25% per side on the theory that PD should dominate. Dropped once the operator's taste file made the implication of that cap clear: roughly half the named favorites (Brumaru, Dinescu, Cartier-Bresson, Doisneau, Iancu, Warhol, Hopper, 20th-century poetry in general) live in the personal-library tier. A 25% cap would mean the device cannot reflect the operator.

Rationale: the tier's legal obligations (citation, no distribution, operator-controlled backup) are enforced item-by-item by `corpus-schema` and `add-corpus-ingestion`. Nothing requires enforcement at the corpus-mix level. The audit still records the tier breakdown so the posture is visible; no ratio is enforced.

A weaker companion rule survives: when a canonical work exists in both PD and personal-library form (e.g., Hiroshige), prefer the PD routing. That's a plain quality decision (the Met's TIFF is higher resolution than a web JPEG), not a legal one.

Alternative considered: keep the ceiling, lower it to something like 50%. Rejected because any hard ceiling rejects works the operator actually wants, and no ratio meaningfully improves the legal posture — that posture is already secured by the tier's invariants, not by headcount.

### 25% Romanian text minimum (down from 30%)

Rationale: the dashboard is explicitly bilingual. Without a floor, English-language text sources dominate by availability, and Romanian presence becomes token. 25% is an honest presence threshold — enough to feel like a bilingual device, low enough that the operator's Romanian-poet canon (Dinescu, Brumaru, Eminescu, Blaga, Arghezi, Cărtărescu short prose) carries the share without straining for coverage. Image content has no language dimension, so this requirement applies only to text.

Alternative considered: 30% (the earlier draft). Revised downward because the Romanian poet canon available via canonical lists is finite and roughly sized; asking for 30% would force including marginal entries to hit the floor. 25% lets the Romanian share rest on canonical works alone.

### 30 nocturne items minimum (down from 60)

One month of nightly rotation before repetition feels right for an ambient night mode. Fewer and repetition is noticeable; more is icing. Nocturne items are typically architectural or landscape photographs with large dark areas — a separate curation discipline from main Gallery images. At canonical-list scale, 30 items amounts to two nocturne lists (e.g., Whistler nocturnes + Brassaï night-Paris + Atget nocturnes + Hiroshige rain-and-moon selections).

### Canonical list files are committed; the log is narrative

Two records of the corpus history coexist:

- **List files** under `openspec/changes/build-seed-corpus/lists/*.yaml` are the curatorial artifacts — what was proposed, what was approved. Git diff shows exactly how taste was expressed.
- **Log** at `openspec/changes/build-seed-corpus/log.md` is append-only human prose per batch. Why this list happened now, why a particular item was pruned, why an amendment was opened. Machine audits cannot capture this; the log is where it lives.

Rationale: a year from now, the operator will want both — the factual "what's in the corpus" (list files + sidecars) and the narrative "why it came to look like this" (log).

### Native-monochrome source preferred

The Inkplate 10 renders 1-bit dithered. Native-monochrome media — etchings, engravings, lithographs, ink drawings, B&W photography, graphic cutouts — render cleanly and preserve the artist's intended tonal structure. Color paintings get dithered through a gray-conversion step, which flattens exactly the dimension the work was built around (Matisse's reds, Warhol's industrial palette).

Consequence for curation at every phase of this seed:

- When an artist offers both color-painting and B&W-graphic work in their canon (Modigliani's paintings *and* his pencil portraits; Matisse's canvases *and* his cutouts/line drawings; Warhol's color silkscreens *and* his blotted-line drawings), **prefer the B&W-graphic option** for the seed corpus.
- When a color work is load-bearing for the corpus (Warhol's *Campbell's Soup*, Matisse's *Red Studio*, Breitner's Amsterdam) and no B&W-native alternative represents that artist well, **drop it from the seed** rather than accept a dithered-color item. The artist can still appear in the text taste file or via a graphic alternative later.
- When a color work dithers acceptably (ukiyo-e prints, Schiele's drawings-with-wash, Haeckel's high-contrast plates, tonal paintings like Whistler's nocturnes or Hopper's chiaroscuro), **accept-with-evaluation**: run it through the renderer's dither preview and commit only if the dithered output holds the intended reading.

This is not a ban on color — the rendering pipeline will always handle color-to-grayscale gracefully — it is a curatorial posture against pairing with material whose identity is in its chroma.

#### Scenario: Artist has both color and B&W-graphic canonical works

- **WHEN** proposing a Matisse item for the seed, and the artist's canon includes both *The Red Studio* (painting, color-critical) and *Blue Nude II* (cutout, graphic silhouette)
- **THEN** the seed prefers *Blue Nude II*; *The Red Studio* is not proposed

### No schedule

The change stays open indefinitely. It can sit at 60% coverage for a month while the operator does other things. Rationale: forcing a schedule would make the gate feel like a deadline, which produces rushed list approvals and shallow canonical picks. Patience here is a virtue.

## Risks / Trade-offs

- **Open-ended timeline.** The change could drift open for months. Mitigation: other work proceeds in parallel; `experiment-pairing-viability` is the only downstream change it blocks, and it can operate against partial coverage.

- **Web-fetch quality for personal-library items is uneven.** Some canonical works have excellent public reproductions; others don't. Mitigation: per-item quality threshold in the fetcher (documented in `add-corpus-ingestion`), fallback to `corpus ingest-personal` folder mode for specific items that can't be satisfactorily web-fetched, and the list file's candidate URLs let the operator pre-rank known-good sources.

- **Source exhaustion on thin themes.** Themes like `machines-mechanisms` or `procession-ritual` may have fewer canonical items than denser themes. Mitigation: the theme floor is deliberately modest (≥15, not ≥25); if a theme cannot be populated to 15 from canonical lists, the operator can either lower the ceiling via a separate change to the taxonomy, or author a targeted list drawing from Tier-2 PD sources (Smithsonian, Europeana).

- **Vocabulary amendments cascading late.** If an amendment lands near final seed, re-tagging hundreds of prior items is expensive. Mitigation: the vocabulary-stable milestone is placed explicitly as a gate — two consecutive non-amending batches in the mid-corpus range signal the vocabulary is settled before the final push.

- **Anthology-first can become canon-worship.** Sticking rigidly to the best-known works risks a corpus that feels like a greatest-hits playlist. Mitigation: the 10% weird bucket defined by rendering's selection policy pulls in deliberate oddities (Kharms, Haeckel, marginal Cajal drawings, absurdist fragments), and canonical lists can include known-but-lesser-known items the operator specifically values.

- **Personal-library will be the majority tier, and that's fine.** The audit surfaces this plainly rather than hiding it behind a ratio cap. The risk is optics (future readers of the change may assume a lapse) rather than substance; addressed by documenting the decision here and in the proposal.

## Migration Plan

Not applicable in the usual sense — nothing is replaced. Ratification sequence:

1. `add-corpus-schema` archived. Taxonomies exist.
2. `add-corpus-ingestion` archived. Tools work (`propose-list`, `fetch-list`, web-search channel, contact sheet, pruning).
3. This change opens. Operator captures taste file, authors canonical lists, runs batches.
4. Amendments may be proposed as separate changes along the way.
5. Milestones are reached, logged, audited.
6. Final audit passes → this change archives with a final log, a final audit file, and the full set of canonical list files committed.

Rollback is situational: if a batch produces disappointing items, `corpus prune` removes them; if an entire canonical list proves misguided, the sidecars, body files, binaries, and manifest entries for that list can be removed with a log entry. There is no traditional "rollback" of the change itself, short of abandoning the project.

## Open Questions

1. **Cadence of audits.** Per-batch is probably too noisy; monthly may be too rare during early ingestion. Likely answer: after every five batches, plus at each milestone. Defer to execution — let the operator find the useful rhythm.

2. **Handling items that resist clean canonical routing.** Some works span categories (a Miró tapestry-sculpture-print, a Kharms story-that-reads-as-aphorism). Accept them under whichever canonical list most naturally claims them, log the ambiguity. Not a framework issue.

3. **Nocturne curation discipline.** Run a dedicated `nocturne-canon` list proposal, or derive nocturne items from existing-artist lists (Brassaï night-Paris subset, Whistler nocturnes subset)? Probably a mix — a dedicated list captures Atget nocturnes and minor nocturne masters, while artist-level lists contribute their dark-scene selections via the `nocturne` folder routing. Decision during execution.

4. **Whether the taste file is versioned.** The operator's likes/dislikes may evolve. Probably the taste file is just a committed markdown document that gets edited over time; significant shifts get their own change proposals. Not a problem for the seed phase.

5. **Family member preferences.** The operator mentioned family likes/dislikes. Treat them as secondary inputs that soften the canon (don't pick the most abrasive Kharms if it would bother a family member), not as separate list files. Revisit if multi-viewer tuning becomes more structured.
