## Context

The proposal described a per-work fetch flow (`propose-list` drafts work-level entries, `fetch-list` executes). Prototype work on the attribution layer (see `corpus/_staging/attrib_test_*` artefacts in the working session that produced this doc) showed the per-work flow is fragile in ways that are not fixable cheaply:

- **Title hallucination risk.** Claude drafting a 20-item list per photographer invents plausible-sounding titles that don't correspond to real frames (exposed concretely by `izis-montreur-ours` — the fetch layer returned zero attributed hits because the title was never a real Izis work).
- **Lexical-match wrong-image.** A DDG query for `"<Photographer> <title>"` returns lexically matching results that are *different* works by the same photographer, or the same subject by *different* photographers. Seven of ten prototype items hit this failure mode.
- **Orientation sensitivity.** DDG's `layout:Tall|Wide` filter hugely affects result quality, but the correct orientation is often the *reproduction-container* aspect ratio (mat + frame + page margins), not the image's native aspect ratio. Operators can't reliably predict which.
- **Per-work attribution validation is expensive.** Wikipedia-anchor + pHash clustering (prototyped across three iterations) recovered only 3–4/10 items without operator review, and the remaining cases required either human eyeball or Claude vision.

A second probe tested the inverse architecture: query `"<Photographer> best photos"` with the same filters. Attribution became automatic (39–40/40 results named the photographer), usable-yield was 12–26 per 40 across the sample, top-20 images were ~20 distinct (clean pHash spread), and the content was visibly canonical: Lange → Migrant Mother + Dust Bowl, Moriyama → Stray Dog + retrospective plates, Fan Ho → Approaching Shadow + Hong Kong frames, Álvarez Bravo → El peluquero.

This design adopts the harvest-and-prune architecture as primary and demotes per-work fetch to a fallback.

## Primary flow — harvest-and-prune

For each photographer on the approved Stage-1 shortlist:

```
1. Query DDG image search:
     q:       "<Photographer> best photos"
     filters: size:Large, type:photo, color:Monochrome
     (no layout filter — reproduction-container orientations vary; let
      diversity through and sort later)

2. Candidate gate — keep a candidate if all hold:
     - surname present in title / url / image-url (word-boundary match)
     - resolution meets orientation-aware MUST floor from corpus-schema
         landscape: pixel_width  ≥ 1080
         portrait:  pixel_height ≥ 693
     - host not in reject-list: pinterest, pinimg, fbsbx, facebook,
       centerblog, blogspot-hosted-gallery, x.com

3. Deduplicate by pHash (dHash-8, Hamming ≤ 8). Duplicates pick the
   highest-resolution representative; domain allowlist breaks ties.

4. Render a contact sheet:
     corpus/_staging/harvest-<photographer-id>/contact-sheet.html
     corpus/_staging/harvest-<photographer-id>/contact-sheet.md
   with a thumbnail grid, source domain, dimensions, DDG rank, and
   a per-item accept/reject/note control.

5. Operator review. Fast-path: accept/reject only (no metadata editing).
   Slow-path: edit Claude-proposed title or substitute candidate URL.

6. For each accepted item, author the sidecar:
     - Claude-vision call: produce title, year, themes, mood, register,
       form, panel_fidelity from thumbnail + surname + DDG title hint
     - validate all tags against the ratified taxonomy
     - refuse panel_fidelity == color-dependent (defensive; input is
       monochrome-filtered but edge cases exist)
     - write sidecar, fetch full binary, update _manifest.json

7. Cost model, per photographer:
     - operator time:     ~2 min contact sheet review
     - Claude-vision:     ~15 items × $0.002 ≈ $0.03
     - fetch bandwidth:   ~15 × 2 MB ≈ 30 MB
     - wall time:         ~60 s fetch + ~30 s vision + operator
```

Projected scale for the 45 post-30s photographers: ~675 accepted items, ~$1.35 in Claude calls, ~90 minutes of operator review, ~1.3 GB of binaries.

## Secondary flow — targeted-work fetch

Harvest surfaces the consensus canonical frames. It under-surfaces:

- operator-known *specific* frames that matter more than their internet-popularity (e.g., a particular Koudelka Roma portrait the operator wants for an anchor role);
- quieter masterworks not dominant in listicles (late Sudek still-lifes, minor Ronis frames);
- works whose rights-tier distinction matters (Atget's PD originals vs later reprints).

For those, a targeted path remains:

```
query:     "<Photographer> \u2014 <title> [<year>]"    (em-dash)
filters:   size:Large, type:photo, color:Monochrome,
           layout:Tall|Wide|Square  (from stage-2 checklist entry)
accept:    DDG's first candidate that passes the same surname + resolution
           + not-banned gate; pHash-cluster for auto-commit, else flag
           for operator review
```

This is the path `fetch-list` originally described. It now serves the tail, not the primary workflow.

## Stage-2 lists as checklists

The Stage-2 work-level yaml files already authored (`corpus/_staging/works-*.yaml`, ~800 entries across 45 photographers) remain authoritative as a **curatorial checklist**, not as an ingestion plan. Their role in this design:

1. **Ratified aspiration.** The operator-approved list of what the corpus *should eventually contain*. Canonical record of taste.
2. **Post-harvest reconciliation.** After each harvest commit, run a reconciliation pass:

   ```
   for each accepted harvest item X:
     if exists checklist entry Y such that:
         photographer matches, AND
         (fuzzy-title-match(X.title, Y.title) > 0.75
          OR visual-match-via-Claude(X thumbnail, Y description))
     then: mark Y as checked, record mapping X -> Y
   ```

3. **Gap report.** After reconciliation, the unchecked remainder is the targeted-fetch queue. Stage-2 is how we know what's still missing.
4. **Completeness target.** We aim to check off most of the list — the exact fraction is empirical, not a gate. A photographer where harvest surfaces 12 of 18 checklist entries is a good outcome; the remaining 6 go through targeted fetch with expanded queries.

The YAML format of Stage-2 entries is extended with a `status` field populated post-harvest:

```yaml
- id: hcb-behind-gare-saint-lazare
  title: "Derrière la Gare Saint-Lazare"
  year: 1932
  orientation: tall
  status: checked          # or: pending | targeted-fetch-failed | dropped
  checked_by: harvest      # or: targeted-fetch | operator-manual
  committed_id: hcb-behind-gare-saint-lazare
```

## Query-expansion strategies for unchecked items

For checklist items that harvest does not surface, targeted fetch escalates through query variants in order:

1. **Photographer + title** (baseline): `"HCB — Behind Gare Saint-Lazare"`
2. **Add year**: `"HCB — Behind Gare Saint-Lazare 1932"`
3. **Add series/context**: `"HCB — Decisive Moment Gare Saint-Lazare"`
4. **Translate title**: `"HCB — Derrière la Gare Saint-Lazare"` (or English ↔ native)
5. **Add orientation filter** (from checklist): `layout:Tall`
6. **Museum-scope site-restricted**: `"site:moma.org HCB Gare Saint-Lazare"` via DDG's site: operator — tries authoritative sources first
7. **Alternate "best" phrasings** if photographer-scope is acceptable: `"HCB iconic photographs"`, `"HCB masterpieces"`, `"HCB retrospective"`
8. **Subject-keyword only** (last resort): `"HCB puddle leap 1932"` — lexical match on the image's distinctive visual element

Each variant runs until either:
- a candidate passes the gate + pHash-matches an anchor or clusters with ≥ 2 other reputable sources, or
- all variants exhausted → item marked `targeted-fetch-failed`, added to the operator's drop-or-substitute decision queue (per the no-scanning policy, there is no queue-for-scan path).

The operator's decision: drop the entry from the checklist, substitute a comparable frame by the same photographer, or accept a lower-resolution candidate that passed the MUST floor but not the 1800 preference.

## Claude-vision tagging at commit time

Harvest delivers candidate images without operator-supplied titles. Every committed item needs a title, year, and taxonomy tags. Claude-vision fills this in at commit time:

```
system:  ratified corpus/_taxonomy/*.yaml (prompt-cached)
user:    thumbnail + photographer name + DDG title hint

task:
  - Identify the specific work (title, year) if known. Return "unknown"
    if you cannot identify a specific canonical work. Do not guess.
  - Propose themes[], mood[], register[], form — drawn only from the
    ratified taxonomy keys.
  - Propose panel_fidelity: native | robust.
  - If the image is: a portrait of the photographer, a book cover,
    an exhibition poster, or evidently not by this photographer, reply
    REJECT with a one-line reason.

output: strict JSON matching the sidecar schema fields.
```

Rejection reasons map to operator-review queue. Valid responses commit after taxonomy validation.

## Reject-list of hosts (prune at candidate gate)

Pruned unconditionally regardless of other signals:

```
pinterest.com, pinimg.com, in.pinterest.com, *.pinterest.*  (user-uploaded, low trust)
facebook.com, fbsbx.com, fb.com                              (auth-gated, expires)
instagram.com, twitter.com, x.com                            (same)
centerblog.net                                               (observed pattern: user blog scrapes)
alchetron.com, shutterstock.com, alamy.com                   (watermarked / paywall)
```

Low-weight but not banned (candidates considered, domain counts toward cluster consensus only if ≥ 2 other domains agree):

```
*.blogspot.*, *.wordpress.*, tumblr.com, reddit.com, youtube.com
```

Allowlisted with positive boost (score-tier for tiebreakers, not a gate):

```
museums:    moma.org, metmuseum.org, getty.edu, artic.edu, nga.gov,
            tate.org.uk, loc.gov, sfmoma.org, museumca.org, icp.org
archives:   magnumphotos.com, henricartierbresson.org, galerie-roger-viollet.fr,
            irvingpennfoundation.org, dorothealange.museumca.org
auctions:   sothebys.com, christies.com, phillips.com, 1stdibs.com, bukowskis.com
galleries:  fraenkelgallery.com, rosegallery.net, jacksonfineart.com,
            holdenluntz.com, pacegallery.com, obscuragallery.net, souslesetoilesgallery.net
editorial:  artblart.com, aperture.org, blind-magazine.com, loeildelaphotographie.com,
            artsy.net (curator-backed)
wiki:       wikipedia.org, wikimedia.org, commons.wikimedia.org
```

The allowlist is maintained under `pairing/src/inkplate/ingestion/web_search/domain_weights.py` and can be amended without a change proposal — it's an operational list, not a ratified artefact.

## Rejected alternatives

- **Per-work stage-2 as primary fetch plan.** Fails on title hallucination, lexical-match misattribution, and orientation guesswork. Prototype: 4/10 usable at best.
- **Wikipedia-anchor + pHash match as primary validator.** Wikipedia has work-dedicated articles for ~10–20% of 20C canonical photographs (mostly PD: Migrant Mother, Moonrise Hernandez, Pepper No. 30). The remaining 80% land on photographer-biographical articles whose pageimage is the *photographer's portrait*, which then rejects every candidate of the actual work. Cannot be the primary strategy; useful as a validator when applicable.
- **Museum-API allowlist only (no web search).** Excellent for PD tier (Met, Rijksmuseum, Gallica, LoC). Insufficient coverage for 20C copyrighted work, which is most of this corpus. Leaves 80% of the personal_library tier uncollectable.
- **Operator-supplied candidate URLs per work.** Already partially in the ratified spec. Real-world usage during the seed build showed operator-supplied URLs were hit-or-miss (~50% yielded the right image at acceptable resolution). Retained as an accept-with-preference signal but not a primary path.

## Open questions

- **Harvest recall against the stage-2 checklist**. Must be measured across 3–5 pilot photographers before committing to the architecture at full scale. Target: ≥ 50% of checklist entries surfaced via harvest; ≥ 80% after one round of query expansion. If recall is substantially lower (say < 40%) the per-work targeted path must remain co-equal.
- **Claude-vision title-identification accuracy**. Needs ground-truth benchmark on 20 items from the existing corpus where we already know the correct title. If accuracy < 70% on specific-work identification, the Stage-2 checklist reconciliation becomes harder and operator-supplied titles (from checklist match) should override Claude's guess when confidence is tied.
- **Contact sheet UX.** HTML grid is operator-friendly but needs a local server. Markdown with embedded thumbnails is git-friendly but review-unfriendly. Starting with HTML; revisit if operators prefer something else.
- **Orientation filter in harvest.** Current design uses no `layout:` filter on the `best photos` query, reasoning that diversity is a feature. If the panel-fidelity or tagging pipeline shows strong bias toward one orientation per photographer (Vivian Maier square, Lange tall) that may not be corpus-useful, a post-harvest orientation-balance pass could be added. Measure first.

## Impact on tasks.md

Several existing tasks change scope; others are new:

- **Task 2 (Canonical-list proposal)** — descope. `propose-list` becomes `propose-shortlist` at the photographer level (what we did in stage-1). Per-work drafting is no longer the primary artefact, though it remains available as a secondary tool for building stage-2 checklists.
- **Task 5 (fetch-list)** — renames to `harvest-photographer` for the primary flow; targeted per-work fetch retains the existing spec under `fetch-work`.
- **Task 6 (contact sheet)** — unchanged in substance; applies to harvest output, not per-work batches.
- **Task 7 (Claude-tagging)** — promoted from optional `--claude-tag` flag to the default commit path. The folder-mode `ingest-personal` pathway still supports it as optional for operator-uploaded files.
- **New task 14 — Stage-2 reconciliation** — subcommand `corpus reconcile-checklist` that matches committed items against Stage-2 YAML, updates `status` fields, and reports gaps.
- **New task 15 — Query-expansion ladder** — implements the 8-step escalation described above for unchecked checklist items.

The detailed tasks.md update is a separate edit following this design.

## Success criteria

The design is successful when:

1. `harvest-photographer <id>` on a canonical photographer (Lange, HCB, Fan Ho) yields ≥ 10 operator-accepted items in a single operator session (~5 min).
2. `reconcile-checklist` against Stage-2 files shows ≥ 50% of checklist entries ticked from harvest alone; ≥ 80% after one round of targeted-fetch expansion.
3. Claude-vision tag outputs validate against the ratified taxonomy with ≤ 5% rejection rate (higher rejection means vocabulary drift, which should surface as a taxonomy amendment proposal, not a pipeline fix).
4. End-to-end: 45 photographer harvests → ~675 committed items, under 2 hours of operator time, under $5 of Claude spend.
