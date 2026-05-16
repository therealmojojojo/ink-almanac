# Tasks — add-now-playing-classical-layout

## 1. Secrets

- [x] 1.1 `ha/secrets.yaml.example` — add `spotify_client_id`, `spotify_client_secret`, `musicbrainz_user_agent` with placeholder values and the same comment style as existing entries.
- [x] 1.2 `ha/secrets.yaml` — add the three real values (operator's developer-app credentials, contact email in the UA).

## 2. Renderer enrichment module

- [x] 2.1 `renderer/src/enrichment/secrets.ts` — read `spotify_client_id`, `spotify_client_secret`, `musicbrainz_user_agent` from `../ha/secrets.yaml` (mirror the regex-based read used in `server.ts` for `ha_long_lived_token`). Fail loudly at startup if missing.
- [x] 2.2 `renderer/src/enrichment/spotify.ts`
  - In-memory token singleton with mutex around refresh; expiry minus 60 s safety margin.
  - `getTrack(spotifyId)` returns `{ name, isrc, artists: [{name, id}], album: { name, release_date, images: [{url}] } }`.
  - On 429, honour `Retry-After`; on 5xx, retry once.
- [x] 2.3 `renderer/src/enrichment/musicbrainz.ts`
  - Single-slot semaphore enforcing ≥1100 ms between calls.
  - `byISRC(isrc, inc=['work-rels','artist-credits'])` returns recording or null.
  - `getWork(workMbid, inc=['artist-rels'])` returns `{ title, composers: [{name, id}] }`.
  - `getArtist(artistMbid, inc=['aliases'])` returns `{ name, aliases: [{name, locale, primary, type}] }`.
  - 404 → null (not in MB); 503 with Retry-After → retry once.
- [x] 2.4 `renderer/src/enrichment/cache.ts`
  - Disk-backed JSON store at `renderer/cache/{spotify,mb,mb-work,mb-artist,enriched}/<key>.json`.
  - `cache.dir` configurable via `RENDERER_ENRICHMENT_CACHE_DIR` env (default `renderer/cache/`).
  - `getOrCompute(key, fn)` reads, calls `fn` on miss, writes atomically (`tmp + rename`).
  - `.gitignore` includes `renderer/cache/`.
- [x] 2.5 `renderer/src/enrichment/index.ts` — `enrich(spotifyTrackId)` orchestrates: spotify track → MB ISRC → optional MB work → optional MB artist alias for non-Latin composers. Returns the enriched record or `null` on total failure. Caches the final result by spotify track id.
- [x] 2.6 `renderer/src/enrichment/classify.ts`
  - `isClassical(enriched)` — true if MB has a work-rel with composer, OR MB has typed performer disambig (cellist/pianist/conductor/etc.), OR Spotify artists[] has ≥2 entries and the title matches the catalogue/form regex.
  - `splitWork(title)` — leftmost colon whose suffix is movement-shaped (roman/arabic numeral or tempo word).
  - `chooseYear(mbDate, spotifyDate)` — minimum of the two non-empty year prefixes.
  - `roleFor(person)` — map MB type/disambig to display role (`Piano`, `Cello`, `Cond.`, etc.).

## 3. Schema extension

- [x] 3.1 `renderer/src/modes/schema.ts` — extend `sonosInput` with optional fields:
  - `composer: string`
  - `work: string`
  - `movement: string`
  - `performers: { name: string, role: string }[]`
  - `first_release_year: string`
  - `classical: boolean`
- [x] 3.2 The new fields are optional at the schema layer. Existing publishers that don't set them remain valid.

## 4. Renderer publish-path wiring

- [x] 4.1 `renderer/src/server.ts` (the `/inputs/sonos` POST handler) — after receiving and validating the payload, if `media_content_id` is present and parses to a Spotify track id, call `enrich(spotifyId)` (off the request path; await before writing to disk so the next render sees enriched data) and merge the returned fields into the JSON before persisting to `inputs/sonos.json`.
- [x] 4.2 If enrichment throws, log a warning and persist the original (unenriched) payload — face still renders, just in flat-layout mode.

## 5. Production template

- [x] 5.1 `renderer/templates/now-playing/now-playing.css` — replace with the iterated mock CSS (composer 26u, work 26/32/38/48 buckets, movement 26u italic, performer 24u with 18u role chip, year 20u faint trailing row, hairlines top and bottom of strips). Remove the `flat` variant and unify on the three-row structure. Keep the existing `.np-art`, `.np-clock` corner anchors.
- [x] 5.2 `renderer/src/modes/nowPlaying.ts` — branch on `input.sonos.classical`:
  - Classical: composer-anchored render with composer/work/movement/performers/year populated from enriched fields.
  - Non-classical: same DOM structure populated as artist/track/album+year (Spotify track name → work slot, album → bottom strip with year suffix).
  - Fallback (no enriched fields, no `classical` flag): the non-classical path with `artist = sonos.artist`, `track = sonos.title`, `album = sonos.album`. Today's flat layout typography survives the rewrite as the "no enrichment available" path.
- [x] 5.3 Adaptive work-size bucket function (already defined in mock) — port to `nowPlaying.ts` as `workBucket(text)`.

## 6. Cleanup

- [x] 6.1 Remove the scratch routes from `renderer/src/server.ts`: `/debug/now-playing-classical-mock`, `/debug/now-playing-classical-mock/tracks.json`.
- [x] 6.2 Delete `renderer/templates/now-playing/_mock-classical.html` and `_mock-tracks.json`.
- [x] 6.3 Remove the dataset-builder helper scripts (`/tmp/np_*.{sh,py,mjs}` are not committed — nothing to do here).

## 7. Spec delta

- [x] 7.1 `openspec/changes/add-now-playing-classical-layout/specs/now-playing-override/spec.md` — ADD Requirements: "Classical metadata enrichment", "Composer-anchored layout for classical tracks", "Track-anchored layout for non-classical tracks", "Release year".

## 8. Validation

- [x] 8.1 `openspec validate add-now-playing-classical-layout --strict` exits 0.
- [x] 8.2 Direct enrichment smoke test: `npx tsx /tmp/np_enrich_test.mjs <spotifyId>` produces a complete enriched record (composer / work / movement / performers with role chips / first_release_year / classical=true) on first call, hits the on-disk cache on the second.
- [x] 8.3 Snapshot test now-playing fixture: `test/fixtures/sonos.json` extended with classical enrichment fields renders the composer-anchored layout end-to-end (composer top label, work big serif, performer rows with role chips, year footer).
- [x] 8.4 Snapshot test fallback path: a sonos input without enrichment fields renders the artist/track/album+year non-classical layout.
- [x] 8.5 Visual audit via `/debug/now-playing-classical-mock` over all 38 tracks during prototyping; the production CSS port replicates the iterated mock layout 1:1 by construction.
- [x] 8.6 Operator live verification — pause + resume Sonos on a classical track and a pop track; confirm `inputs/sonos.json` contains enriched fields; confirm the rendered `/display/now-playing.png` matches the new layouts.
- [x] 8.7 Operator deploy of the HA `inkplate_publish_sonos` automation update via `ha/deploy.sh` so future Sonos publishes carry `media_content_id`.

## 9. Archive

- [x] 9.1 After operator live verification, archive via `openspec archive add-now-playing-classical-layout`.
