## Context

The corpus-schema change ratifies a structural contract but deliberately delivers no tooling. This change is where the contract meets reality: the operator approves a canonical list per category, `fetch-list` turns that list into sidecars and binaries, and the seed corpus begins to exist.

The ingestion workflow has to satisfy two uncomfortable constraints at once. First, the operator should not become a metadata librarian — hand-curating several hundred items by searching, previewing, and tagging one at a time defeats the project's premise. Second, the corpus is the project's taste, and full automation would produce generic selections that corrode that taste. The design's central decision is **where the taste gate sits**: we place it at list-level (the operator approves a canon before anything is fetched), with a contact-sheet pruning step as the correction valve, rather than at per-item interactive review.

## Goals / Non-Goals

**Goals:**
- Turn an approved canonical list into tagged, stored corpus items with no per-item operator attention.
- Make the list-approval step fast: reading a proposed list of ~30 canonical works should take a minute or two, not an hour.
- Support two acquisition channels cleanly: PD connectors for public-domain works, web search for personal-library works.
- Keep every write gated by corpus-schema validation — no bad sidecar, no bad body file, no manifest drift reaches disk.
- Maintain a clean seam between ingestion (offline, operator-paced, Python) and runtime (daily, non-interactive, TypeScript renderer plus HA automation).
- Handle personal-library legal obligations automatically (tier routing, body-file storage, backup-location restrictions).

**Non-Goals:**
- Per-item interactive review. Taste decisions happen at list-level; corrections happen via post-fetch pruning.
- Broad-query discovery ingestion. The seed workflow is list-driven; freeform "ingest whatever Met returns for Hiroshige" is out of scope.
- Building a web UI. The list proposal is a YAML file the operator edits in any editor; the contact sheet is a generated HTML/Markdown file.
- Embeddings. The tag-based pipeline does not need them; adding embedding generation here would be scope creep.
- Any corpus-size targets. `build-seed-corpus` owns the "how many items" decisions; this change owns the mechanism.

## Decisions

### Anthology-first, not discovery-first

The primary workflow is: Claude proposes a named canonical list per category (a poet's essentials, a photographer's canon, a named Japanese print series, an anthology section); the operator edits the list file; `fetch-list` executes it. Taste lives at the list-approval step, which is fast (a read-through of ~30 names and titles) and editable (the operator can swap in a piece they know should be there, drop one they dislike, fix a tag).

Rationale: the target corpus is small (a few hundred items per side), so every item should simply *be the canon* rather than whatever an arbitrary query surfaces. Long-tail discovery via broad API crawls wastes tagging effort on items that wouldn't make the cut anyway, and it defers taste to per-item decisions where operator fatigue is highest.

Alternative considered: discovery-first with per-item review. Rejected because it reverses the fast/slow: the taste decision is big and infrequent (worth the operator's focused attention), the fetch decision is small and frequent (should be mechanical). Approving a list once is one thoughtful decision; approving 30 items one at a time is 30 semi-attentive decisions that average to less taste, not more.

### Two acquisition channels: PD connectors and web search

The `public_domain` and `cc0` tiers fetch through per-source connectors (Met, Rijksmuseum, Gallica, LoC, Project Gutenberg, Wikisource, Wikimedia Commons). The `personal_library` tier fetches through a general web-search channel that prefers reputable domains and records the actual source URL used.

Rationale: canonical lists refer to specific named works (`hcb-hyeres`, `brumaru-balada-in-do-minor`). For PD works, the canonical source is the institution that holds them. For in-copyright works admitted under private-copy, the canonical source is whatever reputable public reproduction exists on the web — museum sites, artist estates, literary archives, publisher previews.

Alternative considered: book-scan acquisition for personal-library, per the original spec draft. Rejected: the operator does not scan books. Romania Law 8/1996 Art. 34 private-copy exception is satisfied by private non-commercial display irrespective of acquisition channel, so web fetch is fine; and forcing any scan step would make the operator's actual taste (heavy in 20th-century poetry and photography) prohibitively expensive to seed.

Folder-based `corpus ingest-personal` covers the case where the operator has already collected a folder of web-downloaded images or typed text fragments for a category and wants to wire them in as one batch, rather than one-by-one through `fetch-list`. There is no scan path, primary or secondary.

### Tagging at list-proposal time, not at fetch time

Claude is invoked during `corpus propose-list` to produce a complete list document including proposed tags per item. `fetch-list` writes sidecars directly from the list entries; it does not re-invoke Claude unless a list entry is missing required fields (in which case it halts).

Rationale: tagging 30 items during list proposal with the full vocabulary loaded once, using prompt caching, is cheap and fast. Re-tagging during fetch would double the cost, introduce drift between list approval and actual written tags (the operator approved tags A, fetch wrote tags B), and defeat the point of a reviewable list file.

Operator edits to tags in the list file are respected verbatim by `fetch-list`.

### Contact-sheet pruning instead of per-item review

After `fetch-list`, the tool produces a contact sheet (thumbnail grid for images, text excerpts for texts) at `corpus/_staging/<batch-id>/contact-sheet.html`. The operator bans unwanted items via `corpus prune --batch <id> --ban <ids>`.

Rationale: the list approval already concentrated taste decisions; post-fetch pruning catches the few cases where (a) the fetched reproduction was disappointing, (b) the item reads worse at e-paper rendering than expected, (c) the operator changed their mind. Pruning is bulk, fast, and by-id. There's no "edit tags per item" UI because tag edits belong upstream at list approval.

Alternative considered: rich terminal per-item review (`textual` / `rich`). Rejected because it creates exactly the fatigue scenario — tens of terminal screens that each demand attention. A contact sheet is skimmable in seconds.

### Two-phase separation: list approval is step 1, fetch is step 2

Approve-then-fetch is an explicit separation. Rationale: list approval is a low-bandwidth activity (read a YAML file) and should not be gated on multi-megabyte downloads. Fetching runs as a batch job that the operator can background while doing other work. Separating the phases also makes the list file itself the commit-candidate for the curatorial record — list files live under `openspec/changes/build-seed-corpus/lists/` and are reviewable independent of whether the binaries succeeded.

### Sidecars written in a single pass with validation gate

When `fetch-list` processes an item, it validates the final sidecar (including body-file references for personal-library texts) before writing anything. Partial writes are not possible — either the sidecar lands with valid manifest entries, or nothing does. On binary fetch failure, the sidecar is held back (no orphan sidecars without their content), and the list entry is preserved for `corpus fetch-binaries` retry.

Rationale: downstream consumers (pairing pipeline, renderer) should never see a sidecar without its content on disk. Holding the sidecar until fetch succeeds keeps the corpus always-valid.

### Ingestion is a Python CLI, shared package with `pairing/`

Rationale: Python has the best SDKs for the connectors (first-party Anthropic, strong HTTP/YAML/image/search-API handling), and the pairing pipeline is already going to be Python. Keeping both in one package avoids duplicating the Claude-client setup, taxonomy loading, and validation code. The renderer being TypeScript is fine — it consumes the corpus; it doesn't write to it.

Alternative considered: TypeScript ingestion to consolidate with the renderer. Rejected because the Claude SDK ergonomics and the search-API ecosystems are better served in Python, and `pairing/` is already the designated home.

### Vocabulary drift halts list proposal; it does NOT edit taxonomies

Allowing list proposals to invent new terms would bypass the amendment procedure that `corpus-taxonomy` ratified. The `propose-list` step offers map/drop/abort-amend when Claude suggests an out-of-vocabulary tag. The abort path exits non-zero and pushes the operator to open a proper amendment change. This is intentional friction — the small cost of "abort and open an amendment change" is what keeps the vocabulary from fragmenting.

This happens at list proposal rather than at fetch because (a) list proposal is where Claude's tagging happens now, and (b) amendments are best handled before an approved list file exists, not after.

### Backup routing is tier-aware

PD content (`public_domain`, `cc0`) can be backed up to any configured scheme (`file://`, `b2://`, `s3://`, `icloud://`). Personal-library content defaults to operator-controlled schemes only (`file://`, `icloud://`); using `b2://` or `s3://` for personal-library requires an explicit opt-in flag and is discouraged.

Rationale: personal-library's legal posture depends on backups remaining under operator control. A routing default that silently uploaded private-copy material to a commercial cloud bucket would undermine the tier's invariants. Explicit opt-in forces the operator to consider whether that particular cloud location actually counts as "under my control" (e.g., personal-tier B2 bucket with private ACL may be acceptable; shared-tier is not).

### CLI surface is stable; implementation is free

Specs fix the CLI entry points and their behavior (arguments, effects, exit codes). Internal module layout and helper functions are not specified — the apply phase is free to organize the Python code however it wants, as long as the CLI behaves as written.

## Risks / Trade-offs

- **Web-search quality is uneven.** Some canonical works have dozens of high-resolution reproductions on museum sites; others are only available as watermarked low-res thumbnails or behind paywalls. Mitigation: the web channel applies a configurable quality threshold, skips items that fall below it (recording `fetch-failed: no reputable source`), and surfaces them for `corpus ingest-personal` folder-mode fallback. The canonical list pre-ranks candidate URLs per item so the fetcher tries operator-approved sources first.

- **Claude tagging drift across SDK / model updates.** Even with a locked vocabulary, Claude's judgment about which terms apply may shift between versions. Mitigation: every batch report includes a tag-distribution histogram; unexpected shifts become visible and can trigger a targeted re-proposal. List files are committed, so operator-edited tags survive any drift.

- **Rate limits and flakiness of PD sources.** Met and Rijksmuseum have generous limits; Gallica and LoC are more variable; web-search backends have their own quotas. Mitigation: all fetchers retry with exponential backoff; `fetch-list` can resume from where it left off via the list file.

- **Binary fetch at "best available resolution" can be enormous.** High-res museum TIFFs can be 50+ MP. Mitigation: configurable maximum long-edge (default 4096 px), with a `--full-res` override when a specific item benefits from maximum fidelity.

- **Personal-library tier leaks are operator discipline, not a technical guarantee.** `.gitignore` catches accidental commits (including `.body.<lang>.txt` files). The tool's tier-aware backup default catches most accidental external uploads. It cannot prevent an operator from manually copying a `corpus/personal_library/` file elsewhere. Mitigation: documentation, clear labeling in sidecars, explicit opt-in for non-operator-controlled backup schemes on personal-library.

- **Claude API costs during heavy list proposal.** Proposing 20 lists of 30 items each at ~$0.02 per proposal call with taxonomy cached is a few dollars. Large re-proposal cycles (e.g., after a vocabulary amendment) can stack. Mitigation: batch-summary report includes Claude call count and approximate cost; the list file on disk means a re-proposal is only needed when tags drift out of vocabulary, not on every edit.

## Migration Plan

No migration from prior state. On apply:

1. Python package scaffolding under `pairing/` with the `corpus` entry point.
2. Pydantic models for sidecars, taxonomy, manifest, and canonical-list files.
3. Validation module wired to `corpus validate`.
4. Claude list-proposal module with prompt template, structured-output schema, prompt caching for the vocabulary block.
5. PD connector implementations for the seven Tier-1 sources.
6. Web-search channel with reputable-domain preference and quality threshold.
7. `fetch-list` execution flow: routes by tier/source, writes sidecars/body-files/binaries, updates manifest.
8. Contact-sheet generation and `corpus prune`.
9. Personal-library folder mode (`corpus ingest-personal`).
10. Tier-aware backup routing; `corpus restore` with body-file support.

Rollback: remove the `corpus` CLI entry point and the associated package. Any `corpus/_staging/` batch directories can be deleted. Sidecars already written to `corpus/` remain valid because they conform to the ratified schema; no schema changes occur here.

## Open Questions

1. **Which web-search backend.** Brave Search has a reasonable free tier and is privacy-friendly; Bing/SerpAPI alternatives exist. Probably Brave to start; abstract the interface so switching is cheap. Decision deferred to implementation.

2. **Image-quality heuristics for web fetch.** Minimum long-edge, watermark detection, EXIF sanity — where to set the defaults? Leaning: ≥1600 px long-edge, skip items where a detectable watermark covers >5% of the central area. Deferred to implementation and tunable per-batch.

3. **Structured-output mechanism for Claude calls.** Anthropic tool-use or JSON-mode? Decision deferred to implementation; specs only require that proposals are parseable and contain the required fields.

4. **Handling list entries where Claude and the operator disagree sharply on tags.** Accepted approach: operator-edited list wins, period. No tooling to flag "your edit moved this far from Claude's proposal." Revisit if drift becomes a curatorial problem.

5. **Dry-run mode for `fetch-list`.** Useful for estimating binary sizes before committing to fetch. Probably yes; specify in implementation if the operator finds it valuable.
