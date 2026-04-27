> **STATUS — 2026-04-27**: partially shipped. The harvest / commit / reconcile / review loop is in production (`corpus harvest`, `corpus harvest --commit`, `corpus reconcile-checklist`, `corpus review`, `corpus fetch-work`, `corpus ingest-personal --claude-tag`). The automation surface this proposal originally led with — `corpus propose-list`, `corpus fetch-list`, `corpus prune`, `corpus fetch-binaries`, backup upload via `b2://` / `s3://` / `icloud://`, package restructure under `pairing/src/inkplate/ingestion/`, the Pydantic model layer — is **not yet shipped**. Triplet-proposal commands (`propose-triplets`, `review-triplets`, `commit-triplets`) are also unstarted. Operator workflow today is: harvest a creator's work into a staging dir, commit images via Claude-vision tagging, reconcile against an external checklist, then run `corpus review` to capture per-triplet verdicts. That covers ~80 % of the original automation goal but not the "operator self-service propose-and-fetch" surface this proposal called out as primary.

## Why

`add-corpus-ingestion` shipped the load-bearing tools for the ratified seed corpus: `corpus validate`, `corpus audit`, `corpus refetch`, `corpus ingest-personal`, `corpus restore`. What it deliberately omitted was the *automation* layer — the parts that would let an operator build the next corpus without hand-authoring list files, without an agent in the loop for every item fetch, and without manually pruning post-fetch batches.

The seed did not need any of that: the operator worked with the agent directly, the agent picked highest-resolution web copies and authored complete sidecars from URLs, and audit/validate caught drift. That worked for ~400 items and 300 triplets. It will not scale to weekly ongoing curation, nor to re-runs by someone without Claude in the loop, nor to fleet-of-dashboards scenarios.

This change adds the automation that makes ongoing corpus growth operator-self-service.

## What Changes

- **`corpus propose-list --category <name>`** — Claude authors a canonical list file for a named category (poet / photographer / series / anthology section), drawing proposed `id`, `title`, `creator`, `rights_tier`, candidate source URLs, and taxonomy-compliant tags. Prompt-cached on the full vocabulary so repeated calls are cheap. Vocabulary-drift detection: unknown tags halt with map / drop / amend options.
- **`corpus fetch-list --file <path>`** — executes an approved list file end-to-end. Routes PD / CC0 entries through dedicated PD connectors (Met Open Access, Rijksmuseum Studio, Gallica BnF, Library of Congress Prints & Photographs, Project Gutenberg, Wikisource, Wikimedia Commons). Routes `personal_library` entries through a web-search channel with a reputable-domain preference list and resolution ranking. Writes sidecars, downloads binaries and body files, appends manifest entries, uploads to the configured external backup.
- **`corpus prune --batch <id> --ban <ids...>`** — removes sidecars, body files, binaries, and manifest entries for listed ids, with batch-report accounting.
- **`corpus fetch-binaries --batch <id>`** — retries fetch for items whose initial fetch failed, without re-proposing the list.
- **Contact sheet** — after `fetch-list`, render a thumbnail grid (images) + excerpt list (texts) at `corpus/_staging/<batch-id>/contact-sheet.html` to drive pruning.
- **Batch report** — produce `corpus/_staging/<batch-id>/report.md` with counts, tag histogram, coverage delta, failure log, pruning log, Claude call count + approximate cost.
- **`corpus propose-triplets [--count N] [--seed-themes ...]`** / **`corpus review-triplets`** / **`corpus commit-triplets`** — Claude-authored triplet batches with operator contact-sheet review and validating commit. `commit-triplets` auto-fetches any anchor the operator accepted-via-citation that isn't yet in the pool.
- **Claude-tagging in `ingest-personal`** — `--claude-tag` flag that populates `themes` / `mood` / `register` / `form` from an image preview (images) or full content (texts) at stage time.
- **Backup upload at fetch time** — implement the write path for `b2://` / `s3://` / `icloud://` schemes. Personal-library tier routing stays operator-controlled.
- **Pydantic model layer** — typed models for sidecars, taxonomy entries, manifest entries, and list-proposal files; replaces the dict-based validation in `corpus_validate.py`.

## Capabilities

### Modified Capabilities

- `corpus-ingestion`: extended with the automation subcommands above. The ratified CLI surface (validate / audit / refetch / ingest-personal / restore) and the boundary contracts (validation at write, backup URI format, rights-tier routing) carry forward unchanged.

## Impact

- **Runtime deps promoted from optional to required**: `httpx` (HTTP client for connectors + web search), `anthropic` (Claude), `pydantic` (models), `rich` (CLI UX), a web-search backend (Brave Search API initially; pluggable interface).
- **New env / config**: `ANTHROPIC_API_KEY`, `BRAVE_SEARCH_API_KEY` (or equivalent), `CORPUS_BACKUP_SCHEME` + credentials for the configured scheme.
- **Package restructure**: move from the current flat module layout (`pairing/corpus_*.py`) to a proper `pairing/src/inkplate/ingestion/{cli,list_proposal,connectors,web_search,manifest,validate,prune}/` package as module count grows.
- **Tests**: integration tests against real sources (end-to-end `propose-list` → `fetch-list` → `prune` → `audit` dry run per category), plus a `corpus restore` round-trip test against a scratch clone.

## Open questions (to resolve during detailed design)

- Which web-search backend: Brave, Bing, SerpAPI, or a direct per-site scraping fallback? Brave's free tier is probably sufficient for the operator's batch cadence.
- How to scope Claude call cost: prompt-cached vocabulary block is a fixed upfront cost per session, but per-item tagging cost accumulates. Need a budget-halt flag.
- `commit-triplets` auto-fetch: the "accept the triplet, auto-fetch the anchor" pattern is powerful but delegates a fetch decision to the review step. Confirm this is the intended UX before implementing.
