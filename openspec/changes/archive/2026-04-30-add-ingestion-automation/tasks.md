## STATUS: archived as partial / superseded

What shipped: `corpus validate` (full structural + manifest +
sha256), `corpus refetch` (rotate panel-rejected images),
`corpus ingest-personal --folder ... --citation '...'`,
`corpus review`, `corpus audit`, `corpus build-review-page`.
A bespoke web-fetch path was added (`corpus_fetch_web_sources.py`,
`corpus_fetch_web_via_urls.py`) using the Anthropic web-search API
plus URL-then-urllib fallback — different from the proposal's
`corpus propose-list` / `fetch-list` CLI architecture but functionally
covers the operator's ingestion needs.

What did NOT ship: the full curator-side CLI surface
(`propose-list`, `fetch-list`, `prune`, `restore`, binary-manifest
automation). The corpus is being maintained without these — direct
sidecar editing + the existing scripts are sufficient at the
current corpus size.

Revisit if (a) the corpus grows past the point where direct editing
scales, or (b) operator-level governance (multiple curators) becomes
a constraint. The proposal's full design is preserved in this
archived folder.

---

## 0. Architecture note

This task list implements the harvest-and-prune primary flow described in `design.md`. Per-work `propose-list` and `fetch-list` tasks remain in place but are demoted to the secondary (targeted-fetch) path.

## 1. Pydantic model layer

- [-] 1.1 Define pydantic models for image item, text item, personal-library item (with optional `body_files`)
- [-] 1.2 Define pydantic models for taxonomy files (themes, mood, register, form)
- [-] 1.3 Define pydantic models for manifest entries and backup URI variants
- [-] 1.4 Define pydantic models for canonical-list files (Stage-1 photographer shortlist; Stage-2 per-work checklist with `status` field)
- [-] 1.5 Migrate `corpus_validate.py` from dict-based checks to model validation

## 2. Shortlist and checklist proposal

- [-] 2.1 `corpus propose-shortlist --category <name>` — Claude drafts a ranked list of creators (photographers, poets, print series, etc.) for a named category. Output: YAML with `id`, `name`, `years`, `lineage`, `canon_weight`, dedup annotations. This is the Stage-1 artifact.
- [-] 2.2 `corpus propose-checklist --creator <id>` — Claude drafts a per-creator works checklist with `title`, `year`, `orientation`, `distinctive` terms, taxonomy-compliant tags, and a `status: pending` field. Output under `corpus/_staging/works-<creator>.yaml`. This is the Stage-2 artifact.
- [-] 2.3 Both commands use prompt caching on the full taxonomy; drift detection halts with map / drop / amend flow.
- [-] 2.4 Neither command is a precondition for fetch. The harvest flow (Task 5A) works from Stage-1 alone. Stage-2 checklists are consumed by the reconciliation (Task 14) and targeted-fetch escalation (Task 15).

## 3. PD connectors

- [-] 3.1 `FetchResult` record type shared across connectors + web-search channel
- [-] 3.2 `met_open_access` connector (full parity — the ad-hoc calls in `corpus_refetch.py` + operator-pass scripts as baseline)
- [-] 3.3 `rijksmuseum` connector
- [-] 3.4 `gallica_bnf` connector
- [-] 3.5 `loc_pnp` connector
- [-] 3.6 `project_gutenberg` connector
- [-] 3.7 `wikisource` connector with language selection
- [-] 3.8 `wikimedia_commons` connector (full parity — ad-hoc baseline)
- [-] 3.9 Per-connector retry with exponential backoff

## 4. Web-search channel (DDG primary backend)

- [x] 4.1 DDG candidate pool: two-step `vqd` handshake → `i.js` JSON. Filter string `size:Large,type:photo,color:Monochrome` (+ `layout:<Tall|Wide|Square>` when orientation is known). Pluggable for Brave / SerpAPI later. *(Implemented: `pairing/corpus_web_search.py::ddg_search`.)*
- [x] 4.2 **Candidate gate** (keep a candidate iff all hold):
  - surname present in title / url / image-url (word-boundary match, handles short surnames like "Ho" and multi-word like "Álvarez Bravo")
  - resolution meets orientation-aware MUST floor from `corpus-schema`
  - host not in reject-list (pinterest, pinimg, fbsbx, facebook, centerblog, alchetron, shutterstock, alamy, instagram, x.com)
  *(Implemented: `corpus_web_search.py::apply_gate`, `surname_in`, `res_floor`, `BANNED_HOSTS`.)*
- [x] 4.3 **DDG native rank is the primary ordering signal**; domain allowlist is a tiebreaker boost only, not a score multiplier. Retire the v1 custom score formula (`dom × sur × res × phash`). *(Candidates emerge in DDG rank order in `corpus_harvest.py`.)*
- [x] 4.4 `dHash-8` perceptual hash for dedup; cluster-consensus validation for auto-commit still pending. *(Partial: `corpus_web_search.py::dhash`, `cluster_dedup` — dedup done; consensus-validation-as-gate is Phase 2b.)*
- [-] 4.5 Text extraction from candidate pages (readability-style); verbatim excerpt only. Same candidate-gate shape for text items where applicable.
- [-] 4.6 Respect operator-supplied `source_url` candidates declared on checklist entries (try them first, in order).
- [x] 4.7 Fetch-failure taxonomy: `no_surname_match | below_floor | banned_domain | vision_rejected`. Remaining reasons (`no_cluster_consensus | all_queries_exhausted`) ship with the targeted-fetch path. *(Partial: reject reasons populated on `Candidate.reject_reason`; vision-rejection tracked in commit report.)*

## 5A. Harvest-photographer flow (primary)

- [x] 5A.1 `corpus harvest <creator-id>` — constructs query `"<Creator> best photos"`, runs DDG with filters from 4.1, applies candidate gate from 4.2, dedups via 4.4. Output: up to ~40 candidates → ~15–25 usable. *(Implemented: `pairing/corpus_harvest.py::run_harvest`.)*
- [x] 5A.2 Renders contact sheet (Task 6) at `corpus/_staging/harvest-<creator>/contact-sheet.{html,md}`. *(Implemented: `render_contact_sheet`.)*
- [x] 5A.3 On operator accept (via `decisions.yaml`): `corpus harvest --commit <creator>` runs Claude-vision tagging (Task 7), fetches full binary, writes sidecar to `corpus/personal_library/`, updates `_manifest.json`. *(Implemented: `run_commit`, `vision_tag`, `build_harvest_sidecar`, `append_manifest_entry`.)*
- [x] 5A.4 Refuses `panel_fidelity: color-dependent` defensively — Claude vision system prompt instructs reject with `reject_reason: color_dependent`; validator also rejects `color-dependent` at commit time.
- [x] 5A.5 Batch report: per-photographer counts, rejection-reason histogram, orientation distribution (harvest phase) + committed/rejected/errors/cost (commit phase). *(Implemented: `render_report` + `commit-report.md`.)*

## 5B. Fetch-work flow (secondary, targeted)

- [-] 5B.1 `corpus fetch-work --checklist <file> --id <entry-id>` — targeted per-work fetch used for Stage-2 entries not surfaced by harvest. Query: `"<Creator> — <title> <year>"` (em-dash). Filter: includes `layout:` from checklist.
- [-] 5B.2 Same candidate gate + pHash-cluster validation as 5A; writes `pending-fetch` entry in batch report on failure.
- [-] 5B.3 Max long-edge rule (default 4096 px; `--full-res` override); refuse list entries flagged `panel_fidelity: color-dependent`.
- [-] 5B.4 `corpus fetch-binaries --batch <id>` retry path (unchanged from original proposal).

## 6. Contact sheet + pruning

- [x] 6.1 HTML + markdown contact sheet at `corpus/_staging/<batch-id>/contact-sheet.{html,md}`. Per item: thumbnail, dimensions, DDG rank, source domain. Accept controls via `decisions.yaml` (operator flips `accept: true` for items to commit). *(Implemented in `corpus_harvest.py::render_contact_sheet` + `render_decisions_yaml`.)*
- [-] 6.2 `corpus prune --batch <id> --ban <ids...>` removes sidecars, body files, binaries, manifest entries; appends a ban record to the batch report. Also supports harvest batches.

## 7. Claude-vision tagging at commit (required commit path)

- [x] 7.1 At commit time for every accepted harvest or fetch-work item:
  - Claude-vision call (`claude-haiku-4-5`): thumbnail + creator name + DDG title hint → proposes `title`, `year`, `themes[]`, `mood[]`, `register[]`, `form`, `panel_fidelity`, `confidence`, `notes`.
  - Rejects with reason when image is: portrait of the photographer, book cover, exhibition poster, color-dependent, unreadable, or evidently not by this creator.
  *(Implemented: `corpus_harvest.py::vision_tag` with prompt-cached taxonomy system prompt.)*
- [x] 7.2 Taxonomy validation runs after Claude proposal; drift halts commit with a per-item error in the batch report. *(Implemented: `validate_vision_response`; drift surfaces as `taxonomy_errors: [...]` in `commit-report.md`.)*
- [-] 7.3 `corpus ingest-personal --claude-tag` remains available for the folder-mode pathway as an optional flag (unchanged from current ratified spec).
- [x] 7.4 Budget-halt flag — `corpus harvest --commit --max-budget-usd <N>` aborts before exceeding the declared ceiling. Per-call cost estimate is a compile-time constant (`VISION_COST_USD = 0.002` for Haiku 4.5). *(Implemented; applies to harvest. Extends to future Claude-calling subcommands by import.)*

## 8. Upload-to-backup at fetch time

- [-] 8.1 Implement `b2://` upload client
- [-] 8.2 Implement `s3://` upload client
- [-] 8.3 Implement `icloud://` verification (operator-local mount; fallback to `file://` if mount not present)
- [-] 8.4 Personal-library-tier routing refuses `b2://` / `s3://` without explicit opt-in

## 9. Batch report

- [-] 9.1 Generate `corpus/_staging/<batch-id>/report.md` at end of harvest or fetch-work batch.
- [-] 9.2 Sections: counts (candidates / accepted / rejected / fetch-failed), tag histogram, coverage delta (per theme, per creator), fetch-failure log by reason, Claude call count + cost, stage-2-checklist reconciliation delta (how many entries checked by this batch).

## 10. Triplet proposal workflow

- [-] 10.1 `corpus propose-triplets [--count N] [--seed-themes ...] [--out path]` — Claude-authored triplet batch drawing from the current pool
- [-] 10.2 `corpus review-triplets --file <path>` — operator contact sheet with accept / reject / edit-note / edit-nocturne
- [-] 10.3 `corpus commit-triplets --file <path>` — validates and writes accepted triplets to `corpus/_triplets/`
- [-] 10.4 Auto-fetch-anchor: when an accepted triplet names an anchor by citation that isn't in the pool, commit step auto-fetches via web-search channel before writing the triplet

## 11. Vocabulary drift handling

- [-] 11.1 Drift surfaces from `propose-shortlist`, `propose-checklist`, and Claude-vision tagging at commit (Task 7). Each offers: map to existing / drop the tag / abort and amend.
- [-] 11.2 Drift log written to the batch report for curatorial history.

## 12. Package restructure

- [-] 12.1 Move from flat `pairing/corpus_*.py` to `pairing/src/inkplate/ingestion/{cli,propose,harvest,fetch_work,connectors,web_search,manifest,validate,prune,triplets,reconcile}/` package tree
- [-] 12.2 Preserve CLI entry point name `corpus`; subcommand dispatch moves into the package.

## 13. Integration

- [-] 13.1 End-to-end pilot: `harvest-photographer` against 3 canonical creators (e.g., Lange, Fan Ho, Koudelka) — measure usable-yield per batch, Claude-vision tag accuracy vs ground truth, operator time per batch.
- [-] 13.2 Full harvest across the 45-creator post-30s shortlist. Target: ~675 accepted items, ≤ 2 hours operator time, ≤ $5 Claude spend.
- [-] 13.3 `corpus restore` round-trip against an external backup (B2 or iCloud) in a scratch clone.
- [-] 13.4 Personal-library dry run via DDG channel: propose → harvest → confirm body-files produced for text items, no inline-text leaks.

## 14. Stage-2 reconciliation

- [-] 14.1 `corpus reconcile-checklist --creator <id>` matches committed sidecars against the Stage-2 YAML for that creator. Match logic: creator matches AND (fuzzy-title-match ≥ 0.75 OR Claude-vision cross-check of thumbnail vs checklist description).
- [-] 14.2 Updates `status` field on matched checklist entries (`pending` → `checked`), records `committed_id` and `checked_by` (`harvest` / `targeted-fetch` / `operator-manual`).
- [-] 14.3 Emits a reconciliation report: percentage of checklist entries checked, unchecked items listed by id for targeted-fetch escalation.
- [-] 14.4 `corpus reconcile-checklist --all` runs across every Stage-2 file and emits an aggregate coverage dashboard.

## 15. Query-expansion ladder for unchecked items

- [-] 15.1 `corpus fetch-work --escalate` applies up to 8 query variants in order: (1) photographer + title, (2) + year, (3) + series/context, (4) translated title, (5) add orientation filter from checklist, (6) site-restricted museum-scoped query, (7) alternate "best/famous/iconic" phrasings, (8) subject-keyword-only lexical fallback.
- [-] 15.2 Each variant runs against the candidate gate (Task 4.2) independently; first variant to pass → commit.
- [-] 15.3 After all variants exhausted: mark checklist entry `status: targeted-fetch-failed` and add to operator's drop-or-substitute queue. Per the no-scanning policy, there is no queue-for-scan path.
- [-] 15.4 Instrument the ladder: which variant succeeds for each item, so the ladder's ordering can be tuned from actual data.
