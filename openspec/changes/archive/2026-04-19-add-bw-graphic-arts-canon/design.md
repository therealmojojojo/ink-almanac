# Design — API-first source routing

## Decision

Fetching for this change SHALL use museum/archive APIs only. We tested every
named archive and dropped the three creators whose canon exists only behind
non-API or permission-gated walls.

### Context

The photographer pipeline hit ~13% title-match on its first pass because it
fronted a DuckDuckGo image harvest with a Claude-vision post-gate. That
post-gate caught the wrong-author mistakes but did nothing about the quality
ceiling — DDG-indexed scans are mid-res by the time they reach social sites.

The operator's standing rule — *image quality > rights tier, pick highest-res
regardless of copyright* — combined with the specific rule for this change
— *drop items we cannot source at quality rather than ship low-res* — means
we front-load the source vetting before fetch, not after.

## Source probe (2026-04-19)

Each candidate archive was probed with a real request. Table below records
what the test showed.

| source_key              | API? | Auth       | Test result                            | Verdict for this change |
|-------------------------|------|------------|----------------------------------------|-------------------------|
| met_open_access         | yes  | none       | 200, full JSON, ≥3000px images         | **Primary**             |
| artic                   | yes  | none       | 200, IIIF URLs (arbitrary resolution)  | **Primary**             |
| cleveland_museum_of_art | yes  | none       | 200, JSON; 119 Rembrandts with images  | **Primary**             |
| wikimedia_commons       | yes  | none       | 200; returned Daumier *Rue Transnonain* at 4000×2827 (9.8 MB) — NGA scan | **Primary** (aggregator) |
| va_museum               | yes  | none       | 200; 63 Beardsley Salomé records       | **Primary**             |
| bnf_gallica             | yes  | none (SRU) | 200 XML; Callot hits returned          | **Primary** (IIIF)      |
| rijksmuseum             | yes  | key (free) | Demo key rejected; requires registration| **Deferred** until key registered |
| harvard_art_museums     | yes  | key (free) | `demo` key returned 401                | **Deferred** until key registered |
| smithsonian_open_access | yes  | key (free) | `demo` key returned API_KEY_INVALID    | **Deferred** until key registered |
| british_museum          | partial | none     | Collection search exists; image sizes vary | **Fallback**         |
| loc_ppoc (loc.gov)      | yes  | none       | Cloudflare blocks script User-Agents (HTML challenge returned) | **Blocked** |
| internet_archive        | yes  | none       | Metadata + page-image API available     | **Primary** (for book-scan material) |
| all other `<institution>_museum` sources in the works files | no | — | No API; would require HTML scraping | **Not usable for this change** |

## Source routing per creator

Each creator's works are fetched in a priority order. If primary returns no
match at or above the 1800-px long-edge preference, fall through to fallback.
If no source returns a match at floor (1200-px short edge), the item is
marked `status: dropped` and the per-creator floor (Stage-1
`canon_weight`) is re-evaluated.

### Kept — full API coverage available

| creator                       | primary → fallback                                    |
|-------------------------------|-------------------------------------------------------|
| albrecht-durer                | met → commons → cleveland                             |
| rembrandt-van-rijn            | met → cleveland → commons                             |
| jacques-callot                | met → bnf_gallica → commons                           |
| giovanni-battista-piranesi    | met → artic → commons                                 |
| francisco-goya                | met → artic → commons                                 |
| william-blake                 | commons → met                                         |
| honore-daumier                | commons → met → artic                                 |
| gustave-dore                  | internet_archive (book scans) → commons               |
| charles-meryon                | met → artic → cleveland → commons                     |
| odilon-redon                  | artic → met → cleveland → commons                     |
| james-mcneill-whistler        | artic → met → commons                                 |
| aubrey-beardsley              | va_museum → commons → met                             |
| henri-de-toulouse-lautrec     | met → artic → commons                                 |
| edvard-munch                  | commons → met → artic                                 |
| kathe-kollwitz                | met → commons (Harvard deferred)                      |
| edward-hopper                 | met → commons                                         |
| martin-lewis                  | met → commons                                         |
| lynd-ward                     | internet_archive (novel scans) → commons              |
| georges-seurat                | met → artic → commons                                 |
| egon-schiele                  | commons → met                                         |
| sesshu-toyo                   | met → commons                                         |
| hakuin-ekaku                  | met → commons                                         |

### Kept with reduced coverage expectation

| creator                       | primary → fallback                       | Note                                                |
|-------------------------------|------------------------------------------|-----------------------------------------------------|
| otto-dix                      | commons → met                            | Dix's *Der Krieg* is widely scanned on Commons at high res; Harvard has the best plate set but is key-gated |
| ernst-ludwig-kirchner         | commons → met                            | MoMA holdings dominate; no API. Commons has most canonical woodcuts |
| pablo-picasso                 | cleveland → met → commons                | Pre-1927 Picasso (Frugal Repast, etc.) is PD; later Vollard Suite / Bull / Dove are behind copyright — fetchable via Commons where the image has been uploaded, personal_library tier |

### Dropped — no API, or only non-extractable archives

| creator           | lineage         | Reason                                                          |
|-------------------|-----------------|-----------------------------------------------------------------|
| william-kentridge | contemporary    | Charcoal stills from *Drawings for Projection* live on gallery / museum pages with no public API; stills are not uploaded to Commons. No way to fetch at scale with quality guarantee. |
| vija-celmins      | contemporary    | Gallery sites (Matthew Marks) and MoMA hold her graphite/mezzotints but expose no API. Commons holdings are thin and mostly thumbnails. |
| saul-steinberg    | pen-and-ink     | Saul Steinberg Foundation asserts tight control; no API, and most reproductions on the web are low-res magazine-cover crops. |

This removes the `contemporary` and `pen-and-ink` lineages from the canon in
its current iteration; they can return in a later change if (a) a usable
API is published, or (b) the operator opts into a one-off manual fetch
pass for a small, curated subset.

## Result

| Before | After |
|--------|-------|
| 28 creators | 25 creators |
| 9 lineages  | 7 lineages |
| ~183 works   | ~166 works |

## Implementation

The fetch tool SHALL accept a per-creator ordered list of source keys and
SHALL iterate them in order until a strict artist+title match is found at
or above the resolution floor. The existing `pairing/corpus_refetch.py`
already implements `commons` + `artic` + `met` with a strict-match
predicate; this change extends the set to include `cleveland`,
`va_museum`, `bnf_gallica`, and `internet_archive`, and switches the
per-creator order from a hard-coded triple to the table above.

Rijksmuseum / Harvard / Smithsonian are parametrised but skipped when the
relevant API-key env var is unset. The operator MAY register and populate
those keys later; doing so unlocks higher-quality Dürer/Rembrandt (Rijks),
Kollwitz/Dix/Beardsley (Harvard), and Whistler-Venice-Set (Smithsonian
Freer) without further code changes.

## Test results (2026-04-19)

Ran `pairing/test_api_fetch.py` against 9 targets across 3 sources.

| source  | attempts | direct hits | resolution range         |
|---------|----------|-------------|--------------------------|
| met     | 3        | **3/3**     | 1673–3759 long edge      |
| commons | 3        | **3/3**¹    | 3648–5472 long edge      |
| artic   | 3        | 0/3         | — image fetch blocked    |

¹ Commons initially returned 3/3 but one hit (Ratapoil) required a
retry after a rate-limit cooldown; ultimately recovered at 3648×5472.

### Material finding: AIC is metadata-only for scripted fetches

The AIC metadata API at `api.artic.edu` works without headers. The IIIF
image endpoint at `www.artic.edu/iiif/2/...` is fronted by Cloudflare
and returns 403 with `cf-mitigated: challenge` to any non-browser client,
regardless of requested size (native, `!2400,2400/`, `843,/`, etc.).

This changes AIC's role in the routing stack. Retained as a **metadata
index** (i.e., discovery of canonical titles, accession numbers, year,
classification) but image fetch falls back to **Wikimedia Commons**
using the AIC-discovered title.

### Material finding: Commons needs pacing

Commons enforces a per-client rate limit (HTTP 429) at roughly 8–10 image
requests per minute per client. The fetcher SHALL pace Commons requests
at ≥ 5 s between image downloads and retry after 30 s on 429. The
fetcher SHALL prefer the stable `upload.wikimedia.org` URL returned by
the `imageinfo` API rather than constructing URLs.

### Material finding: Met is the strongest primary

Met returned strict artist+title matches at 1673–3759 long-edge on every
Dürer target including one (*Praying Hands*) that exists across the
web mostly as low-res thumbnails. Met has them at archival resolution
(1673×2138 for the drawing; 2656×3749 and 2733×3759 for the prints).
This confirms Met as the preferred primary for old-master prints and
drawings whenever the work is in their collection.

## Rijks via Commons-bridge (2026-04-19)

Rijksmuseum OAI-PMH is **not a per-work search API** — it's a bulk-harvest
protocol that requires opaque numeric IDs (e.g., `id.rijksmuseum.nl/200106086`)
rather than accession numbers (`RP-P-OB-1237`). `GetRecord` with accession
numbers returns `idDoesNotExist`. No SPARQL endpoint is exposed either (404).

However, Wikimedia Commons aggregates Rijks' archival scans and labels them
with the Rijks accession number in the filename (`RP-P-OB-*`, `RP-F-*`,
`SK-A-*`, or explicit "Rijksmuseum"). A Commons-search ranked to prefer those
filenames delivers Rijks-quality without a key.

Test: ran Dürer + Rembrandt via Commons-with-Rijks-preference.

| work                             | resolution  | bytes      | source                          |
|----------------------------------|-------------|------------|---------------------------------|
| Rembrandt *Three Crosses*        | 5386×4117   | **54.5 MB** | Rijks direct                   |
| Dürer *Melencolia I*             | 4918×6257   | **17.9 MB** | Google Art Project (ultra-res) |
| Dürer *St Jerome in the Wilderness* | 2801×4000 | 15.3 MB    | NGA                             |
| Rembrandt *Three Trees*          | 6340×4910   | 7.9 MB     | Rijks `RP-P-OB-444`            |
| Dürer *Apocalypse: Whore of Babylon* (via Met earlier) | 2733×3759 | 4.1 MB | Met |
| Rembrandt *Hundred Guilder Print* | 5022×3648  | 3.9 MB     | museum scan                     |
| Dürer *Knight, Death and Devil*  | 5684×3896   | 3.2 MB     | Rijks `RP-F-2001-7-34-3`       |
| Dürer *Nemesis* (via Met earlier)| 2656×3749   | 2.8 MB     | Met                             |

6/6 direct hits on the Rijks-preferring pass. Several works exceeded what
the classic Rijks API would have returned (the Google Art Project and NGA
scans of Melencolia and St Jerome are among the highest-resolution
photographs of those prints available anywhere).

## Revised routing (post-test)

| creator / group                | primary     | fallback          |
|--------------------------------|-------------|-------------------|
| Old Masters (Dürer, Rembrandt, Callot, Piranesi, Goya) | met | commons |
| 19c print (Daumier, Redon, Whistler, Meryon, Blake)    | commons | met (AIC metadata-only) |
| Doré (book scans)              | internet_archive | commons |
| Lynd Ward (book scans)         | internet_archive | commons |
| Fin-de-siècle (Beardsley, Lautrec, Munch) | met | commons (V&A key-gated deferred) |
| Kollwitz, Dix, Kirchner        | commons | met       |
| Hopper, Martin Lewis           | met         | commons   |
| Seurat, Schiele, Picasso       | met         | commons   |
| Sesshū, Hakuin                 | met         | commons   |

## Test plan

Before full rollout, the fetcher SHALL be exercised on 3 creators across
3 distinct primary sources:

1. **Albrecht Dürer** — source: `met` — target works: *Praying Hands*,
   *Nemesis / The Great Fortune*, *Apocalypse: Whore of Babylon*.
2. **Odilon Redon** — source: `artic` — target works: *Germination* (Origins),
   *Hommage à Goya: Marsh-Flower*, *Origins: First vision*.
3. **Honoré Daumier** — source: `wikimedia_commons` — target works:
   *Gargantua*, *Legislative Belly*, *Ratapoil*.

Success criteria per work: strict artist+title match, long-edge ≥ 1800 px
at fetch, short-edge ≥ 1200 px. Per-run report records matched URL,
resolution, and file bytes.
