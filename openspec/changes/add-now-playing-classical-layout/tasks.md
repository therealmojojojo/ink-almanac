# Tasks — add-now-playing-classical-layout

## 1. Secrets

- [x] 1.1 `ha/secrets.yaml.example` — add `spotify_client_id`, `spotify_client_secret`, `musicbrainz_user_agent` with placeholder values and the same comment style as existing entries.
- [x] 1.2 `ha/secrets.yaml` — add the three real values (operator's developer-app credentials, contact email in the UA).

## 2. Renderer enrichment module

- [ ] 2.1 `renderer/src/enrichment/secrets.ts` — read `spotify_client_id`, `spotify_client_secret`, `musicbrainz_user_agent` from `../ha/secrets.yaml` (mirror the regex-based read used in `server.ts` for `ha_long_lived_token`). Fail loudly at startup if missing.
- [ ] 2.2 `renderer/src/enrichment/spotify.ts`
  - In-memory token singleton with mutex around refresh; expiry minus 60 s safety margin.
  - `getTrack(spotifyId)` returns `{ name, isrc, artists: [{name, id}], album: { name, release_date, images: [{url}] } }`.
  - On 429, honour `Retry-After`; on 5xx, retry once.
- [ ] 2.3 `renderer/src/enrichment/musicbrainz.ts`
  - Single-slot semaphore enforcing ≥1100 ms between calls.
  - `byISRC(isrc, inc=['work-rels','artist-credits'])` returns recording or null.
  - `getWork(workMbid, inc=['artist-rels'])` returns `{ title, composers: [{name, id}] }`.
  - `getArtist(artistMbid, inc=['aliases'])` returns `{ name, aliases: [{name, locale, primary, type}] }`.
  - 404 → null (not in MB); 503 with Retry-After → retry once.
- [ ] 2.4 `renderer/src/enrichment/cache.ts`
  - Disk-backed JSON store at `renderer/cache/{spotify,mb,mb-work,mb-artist,enriched}/<key>.json`.
  - `cache.dir` configurable via `RENDERER_ENRICHMENT_CACHE_DIR` env (default `renderer/cache/`).
  - `getOrCompute(key, fn)` reads, calls `fn` on miss, writes atomically (`tmp + rename`).
  - `.gitignore` includes `renderer/cache/`.
- [ ] 2.5 `renderer/src/enrichment/index.ts` — `enrich(spotifyTrackId)` orchestrates: spotify track → MB ISRC → optional MB work → optional MB artist alias for non-Latin composers. Returns the enriched record or `null` on total failure. Caches the final result by spotify track id.
- [ ] 2.6 `renderer/src/enrichment/classify.ts`
  - `isClassical(enriched)` — true if MB has a work-rel with composer, OR MB has typed performer disambig (cellist/pianist/conductor/etc.), OR Spotify artists[] has ≥2 entries and the title matches the catalogue/form regex.
  - `splitWork(title)` — leftmost colon whose suffix is movement-shaped (roman/arabic numeral or tempo word).
  - `chooseYear(mbDate, spotifyDate)` — minimum of the two non-empty year prefixes.
  - `roleFor(person)` — map MB type/disambig to display role (`Piano`, `Cello`, `Cond.`, etc.).

## 3. Schema extension

- [ ] 3.1 `renderer/src/modes/schema.ts` — extend `sonosInput` with optional fields:
  - `composer: string`
  - `work: string`
  - `movement: string`
  - `performers: { name: string, role: string }[]`
  - `first_release_year: string`
  - `classical: boolean`
- [ ] 3.2 The new fields are optional at the schema layer. Existing publishers that don't set them remain valid.

## 4. Renderer publish-path wiring

- [ ] 4.1 `renderer/src/server.ts` (the `/inputs/sonos` POST handler) — after receiving and validating the payload, if `media_content_id` is present and parses to a Spotify track id, call `enrich(spotifyId)` (off the request path; await before writing to disk so the next render sees enriched data) and merge the returned fields into the JSON before persisting to `inputs/sonos.json`.
- [ ] 4.2 If enrichment throws, log a warning and persist the original (unenriched) payload — face still renders, just in flat-layout mode.

## 5. Production template

- [ ] 5.1 `renderer/templates/now-playing/now-playing.css` — replace with the iterated mock CSS (composer 26u, work 26/32/38/48 buckets, movement 26u italic, performer 24u with 18u role chip, year 20u faint trailing row, hairlines top and bottom of strips). Remove the `flat` variant and unify on the three-row structure. Keep the existing `.np-art`, `.np-clock` corner anchors.
- [ ] 5.2 `renderer/src/modes/nowPlaying.ts` — branch on `input.sonos.classical`:
  - Classical: composer-anchored render with composer/work/movement/performers/year populated from enriched fields.
  - Non-classical: same DOM structure populated as artist/track/album+year (Spotify track name → work slot, album → bottom strip with year suffix).
  - Fallback (no enriched fields, no `classical` flag): the non-classical path with `artist = sonos.artist`, `track = sonos.title`, `album = sonos.album`. Today's flat layout typography survives the rewrite as the "no enrichment available" path.
- [ ] 5.3 Adaptive work-size bucket function (already defined in mock) — port to `nowPlaying.ts` as `workBucket(text)`.

## 6. Cleanup

- [ ] 6.1 Remove the scratch routes from `renderer/src/server.ts`: `/debug/now-playing-classical-mock`, `/debug/now-playing-classical-mock/tracks.json`.
- [ ] 6.2 Delete `renderer/templates/now-playing/_mock-classical.html` and `_mock-tracks.json`.
- [ ] 6.3 Remove the dataset-builder helper scripts (`/tmp/np_*.{sh,py,mjs}` are not committed — nothing to do here).

## 7. Spec delta

- [ ] 7.1 `openspec/changes/add-now-playing-classical-layout/specs/now-playing-override/spec.md` — ADD Requirements: "Classical metadata enrichment", "Composer-anchored layout for classical tracks", "Track-anchored layout for non-classical tracks", "Release year".

## 8. Validation

- [ ] 8.1 `openspec validate add-now-playing-classical-layout --strict` exits 0.
- [ ] 8.2 Restart renderer; check logs show `spotify token acquired` and `mb cache loaded` (or equivalent).
- [ ] 8.3 Live: pause + resume Sonos on a known classical track in operator's library. Confirm `inputs/sonos.json` contains enriched fields; confirm the rendered `/display/now-playing.png` matches the mock layout for that track.
- [ ] 8.4 Live: pause + resume on a pop track. Confirm new pop layout draws (artist top, track big, album+year bottom strip).
- [ ] 8.5 Live: with renderer's network blocked (firewall the Spotify+MB egress), confirm Now-Playing still renders today's flat layout (graceful degradation).
- [ ] 8.6 Visual audit via `/debug/now-playing-classical-mock` over all 38 tracks before removing the route.

## 9. Archive

- [ ] 9.1 After live verification, archive via `openspec archive add-now-playing-classical-layout`.
