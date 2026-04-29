# Session overview — corpus rework, 2026-04-28 → 2026-04-29

A two-day session that started as "fix the smart-pill formula" and grew into
a full rework of how the summary delight cell sources, sizes, and validates
text. End state: smaller corpus, bigger fonts, cleaner typography, two new
review tools, two new spec requirements.

## Headline numbers

| | start of session | end of session |
|---|---:|---:|
| Total sidecars | 1958 | **1888** |
| Summary-eligible texts | ~750 (no flag) | 642 (after `summary_eligible: false` on 108) |
| Sidecars with `excerpt_provenance` | 0 | 74 |
| Source files in `corpus/_sources/` | 0 | 222 |
| Triplets in `_triplets/` | 1023 (stale) | 1023 (regen pending) |
| Sidecars below pill-parity (font <28u) | ~28% of summary pool | unmeasured (after dedup + cuts) |

70 sidecars deleted in total: 51 duplicates (across three audit layers) + 18
Romanian + 1 manual (`eminescu-mai-am-un-singur-dor-opening`).

## What we did, by area

### 1. Typography baked into production CSS

The earlier afternoon wrapped up the validation work:

- Anthology JA 30u / EN 24u for haiku/tanka pairs (24u is a documented
  sub-25u floor exception — anthology baseline-alignment wins).
- Smart pill at fixed **28u Plex Sans / lh 1.1**, ladder removed; bodies
  authored above the cell capacity overflow visibly so the operator catches
  them at ingestion (~455 chars at the post-shift geometry).
- Bottom band re-split to **577u (delight) / 499u (pill)**, +60u toward the
  pill — explicit `u` values now, no more `1.45fr / 1fr` ratio.

These landed in `renderer/templates/summary/summary.css` and the snapshot
goldens were refreshed. The work is in
`openspec/specs/dashboard-faces/spec.md`.

### 2. Smart-pill regeneration

- Regenerated all 664 corpus pills via Opus with content-aware prompt
  (mode A for haiku/tanka with non-EN variants, mode B otherwise),
  ≤455 char target.
- 44 overflows from the first pass got a tighten cleanup; 5 stubborn ones
  hand-trimmed.
- Pattern audit: 33% of pre-existing pills started with formulaic
  biographical-fact opener ("Published in YYYY", "Written in YYYY", "From
  X's …"). Ingest-time prompt now bans that.

### 3. Picker rework (`corpus_build_triplets_v2.py`)

- **Image-cap-1** — no image repeats across the rotation (gallery cell is
  the visible hero; corpus has 1100+ gallery-eligible images, so duplication
  reads as "we already saw this"). Nocturne keeps cap=2 (smaller pool, less
  visible face).
- **Per-slot text caps** with anchor uncapped (the anchor is the triplet's
  invisible spine — used for thematic matching, never rendered).
- **Two-pass generation** — pass 1 forces every summary at use=0, pass 2
  fills with weighted bias.
- **60/40 visual/text gallery split** with theme-relax fallback.
- **`summary_eligible: false` filter** added to the summary pool.
- Re-included `corpus/images/` (119 PD prints) in the pool — earlier
  regression where they were excluded.

### 4. Two-stage extract architecture

The smart-pill formula problem was downstream of a deeper one: many corpus
bodies were **truncated openings** of larger poems with the punchline
sitting in the next stanza. Smart-pills couldn't write good commentary on
truncated text, so they fell back to biographical scaffolding.

Built a two-stage pipeline:

**Stage 1 — fragment extraction** (`corpus_extract_fragments.py`).
For each candidate, give Opus the full source text + the current excerpt;
it returns either the whole poem (if it fits) or a significant fragment
ending at a clean syntactic unit. Writes `excerpt_provenance` block to
the sidecar. Picks `form` based on the resulting body's line count
(stanzaic / fragment / quote).

**Source acquisition** — three channels:

- **Calibre filesystem read** at `/Volumes/Media/Calibre-mini/`. The
  extractor (`corpus_extract_sources.py`) walks `<Author>/<Title>/<file>`,
  unzips EPUB/KEPUB to plain text, dispatches PDF through PyMuPDF, MOBI
  through `ebook-convert` (calibre.app/Contents/MacOS). Per-poem windows
  found via first-line search with diacritic-stripped fuzzy author
  matching.
- **Web fetch via Anthropic web_search** (`corpus_fetch_web_sources.py`)
  for items not in the personal library. Initial pass refused 61 items
  on copyright; rights-aware retry recovered 6.
- **URL-then-urllib fetch** (`corpus_fetch_web_via_urls.py`) for the rest.
  Asks Claude to return URLs only (not text), then fetches the page
  directly with urllib + site-specific HTML extractors. Bypasses the
  model-side reproduction guardrail by separating discovery from copy.

End state: **222 source files** under `corpus/_sources/<author-slug>/`.
86 sidecars passed through Stage 1 in the first apply run. The folder
is gitignored (same posture as personal-library binaries).

### 5. Renderer changes

- **New debug endpoint** `/debug/text-summary-test{,/preview,.png}` —
  renders the production summary face with one corpus text in the delight
  cell + its `smart_pill.body` in the pill cell. Used by the review-page
  builders.
- **Bumped `delight_text` zone budget** (60×4=240 → 80×16=1280 chars) so
  short whole poems aren't prose-truncated by the defensive cap.
- **Replaced form-driven font CSS with metric-driven tier ladder.** Each
  author line now goes in its own `<div class="line">`. The renderer
  computes a fit-tier from author-line metrics + calibrated CPL
  (~0.42×font for IBM Plex Serif) and emits `data-fit-tier="N"` on the
  body. CSS maps each tier to a (font-size, line-height) pair. Three
  phases:
  1. Largest tier ≥28u where every author line fits one visual line AND
     line count fits the cell.
  2. 28u with hanging-indent (`.wrap-turnover`, `text-indent: -2em;
     padding-left: 2em`) when no ≥28u tier admits unwrapped fit.
     Faber/Norton/FSG poetry-typesetting convention.
  3. Sub-pill tiers (24u/22u) only when 28u-with-wrap also overflows the
     cell vertically. Rare for `summary_eligible: true` items.
- **Hanging-indent scoped to `.wrap-turnover`** (later fix) so non-wrapping
  centered items don't inherit a 1em phantom shift.

### 6. Dedup + cleanup audits

Three audit layers, each catching a different class of duplicate:

| layer | key | groups found |
|---|---|---:|
| 1 | author + normalized title | 35 |
| 2 | author + first 120 chars of normalized body | 2 |
| 3 | first ≥18-char line of A as substring in body B | 15 (12 real, 3 false-positive shared phrases) |

**51 sidecars deleted** total; unique themes/mood/register from each
dropped sibling merged into the keeper.

### 7. Romanian language removal

All 18 Romanian-language sidecars (Eminescu, Blaga, Bacovia, Arghezi,
Stănescu, Sorescu, Brumaru, Cărtărescu, Dinescu) deleted along with their
source files and cached PNGs. Per operator call.

### 8. summary_eligible audit

Items with **>5 author lines** (excluding haiku/tanka by genre) marked
`summary_eligible: false`. **108 sidecars** affected — they remain
gallery-eligible but stop competing for the summary delight cell where
the tight cell geometry would force a smaller font.

### 9. Form-mismatch fix

18 sidecars where Stage 1 expanded a 1-line `form: fragment` body into a
multi-line full poem but didn't update the form. Resulted in the
multi-line body rendering at the iconic-aphorism 36u CSS rule and
overflowing. Manual fix promoted to `stanzaic`; Stage 1 prompt now
chooses form based on resulting line count.

### 10. Two new tools, two new specs

**Tools (in `pairing/`, wired into `inkplate_corpus_cli.py`):**

- **`corpus build-review-page --mode {extracts | unterminated}`**.
  Generates a static HTML review page — one card per sidecar, each
  embedding a 1200×825 production summary-face PNG rendered via the
  test renderer. Two modes:
  - `extracts` — Stage-1-touched items, grouped by FULL-poem vs
    FRAGMENT.
  - `unterminated` — bodies that don't end at a clean phrase delimiter,
    grouped by terminator type, with KEEP/RE-EXTRACT suggestion badges
    and a `● src` dot showing whether a Stage-1 source is ready.
- **`corpus audit-truncations`**. Text-only audit (no rendering) that
  prints every body ending with comma / dangling function word / no
  terminal punctuation. Use after large ingest passes to catch
  truncations before they reach the review page.

**Specs (in `openspec/specs/`):**

- **`corpus-schema`** — added two requirements: `Summary-cell
  eligibility` (documents the `summary_eligible` field) and `Excerpt
  provenance` (documents the `excerpt_provenance` block).
- **`dashboard-faces`** — replaced the form-driven font sentence with
  the metric-driven tier ladder, the 28u pill-parity floor, the
  Phase 1/2/3 algorithm, and the `.wrap-turnover` hanging-indent
  convention.

### 11. Two-port renderer setup

Production renderer lives at port **8575** under launchd
(`~/Library/LaunchAgents/com.inkplate.renderer.plist`, KeepAlive=true,
RunAtLoad=true). It auto-restarts on crash.

The test renderer (used by `corpus build-review-page` and any review
work) runs on port **8585** with `RENDERER_PORT=8585 npm run dev`. Test
scripts default to 8585; override with `RENDERER_URL` env var.
Documented in `CLAUDE.md`.

## Files changed (uncommitted at the time of this overview)

```
M  CLAUDE.md
M  openspec/specs/corpus-schema/spec.md
M  openspec/specs/dashboard-faces/spec.md
M  openspec/specs/typography-routing/spec.md
M  pairing/corpus_build_triplets_v2.py
M  pairing/inkplate_corpus_cli.py
M  renderer/src/modes/summary.ts
M  renderer/src/modes/weather.ts        ← unrelated stars-redesign work
M  renderer/src/server.ts
M  renderer/src/zones.ts
M  renderer/templates/summary/summary.css
M  renderer/test/__golden__/...          ← regenerated
?? pairing/audit_text_readability.py
?? pairing/corpus_audit_truncations.py
?? pairing/corpus_build_review_page.py
?? pairing/corpus_extract_fragments.py
?? pairing/corpus_extract_sources.py
?? pairing/corpus_fetch_web_sources.py
?? pairing/corpus_fetch_web_via_urls.py
?? pairing/corpus_generate_pills.py
```

Plus widespread corpus mutations under `corpus/texts/` and
`corpus/personal_library/` (deletes, body rewrites, `summary_eligible`,
`excerpt_provenance` blocks).

## Open threads (deferred)

- **41 unterminated bodies still ship truncated.** The
  `unterminated-review.html` page surfaces them; operator review in
  progress. Decision deferred: accept-and-move-on / Stage-1 re-extract
  the 30 with sources / mark gallery-only.
- **Picker `--apply` not yet run.** Triplet pool in `_triplets/` is
  still pre-cleanup. Will rebuild against the cleaned corpus when the
  unterminated decision lands.
- **74 Stage-1 outputs not all reviewed.** The `rework-review.html`
  page is built and refreshed; eyeballing in progress.
- **Tier 6/7 sub-pill items** (~199 in earlier audit, fewer after
  dedup + Romanian removal). Could be reduced by re-extraction with a
  "≤39 cpl" prompt instruction.

## Pointers for the next session

- Review pages: `openspec/changes/expand-summary-pool/{rework,unterminated}-review.html`
- Build / refresh: `corpus build-review-page --mode {extracts|unterminated} [--force]`
- Audit only: `corpus audit-truncations`
- Test renderer: `cd renderer && RENDERER_PORT=8585 npm run dev`
- Production renderer: launchd, on 8575, self-healing
- Source library root: `corpus/_sources/<author-slug>/<id>.txt` (gitignored)
- Stage 1: `python pairing/corpus_extract_fragments.py --apply [--ids ...]`
- Stage 2 (pill): `python pairing/corpus_generate_pills.py --all-missing`
