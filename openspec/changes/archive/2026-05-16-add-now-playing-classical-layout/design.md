# Design — add-now-playing-classical-layout

## Why renderer-side enrichment, not HA-side

Both endpoints can call Spotify and MusicBrainz. The deciding factor is the Spotify Client Credentials token: a 1-hour bearer that needs in-memory caching, expiry detection, refresh-on-demand, and a mutex against concurrent refresh. In Node that's ~30 lines of one module owning one promise. In HA Jinja:

- `input_text` helpers store the token + expiry, requiring an automation to read, branch on expiry, fetch, parse, and write back two helpers before the actual lookup.
- 401 retry adds a second branch reading the same helpers.
- Two automations refreshing in parallel race; coordination requires `mode: queued` plus shared timer state.

The renderer also already reads `ha/secrets.yaml` for the `/ha-proxy` endpoint, so adding two more secret fields uses an established path. HA-side would need a new helper conventions or a sidecar Python script, neither cheap.

Renderer-side wins. HA continues to publish `sonos.json` with the existing fields plus `media_content_id` (already published); the renderer enriches before drawing.

## Data flow

```
HA               renderer                            external
├── publishes    ├── /inputs/sonos.json (POST)
│   sonos.json   │     ↓
│   with         │   parse, extract spotify_id
│   media_       │     ↓
│   content_id   │   enrichment.lookup(spotify_id)
│                │     ├── cache hit → return cached enriched fields
│                │     └── miss      → spotify.getTrack(id)
│                │                       → musicbrainz.byISRC(isrc)
│                │                          ├── work-rel? → musicbrainz.getWork(mbid)
│                │                          └── composer non-Latin? → musicbrainz.getArtist(mbid, inc=aliases)
│                │                       → cache enriched object on disk
│                │     ↓
│                │   merged sonos.json written to inputs/
│                │     ↓
│                └── on render: classical layout if classical:true, flat-layout otherwise
```

The enrichment is synchronous on the publish path. A miss costs ~500–800 ms; the existing publish path's 10 s activation budget absorbs it. Cache hits add a single file read.

## Caching

Disk-backed JSON files under `renderer/cache/`:

```
cache/
  spotify/<track_id>.json       # whole Spotify track payload
  mb/<isrc>.json                # whole MB recording payload
  mb-work/<work_mbid>.json      # whole MB work payload
  mb-artist/<artist_mbid>.json  # whole MB artist with aliases (composers only)
  enriched/<track_id>.json      # final merged enrichment (composer/work/movement/performers/year/classical)
```

All entries are immutable in practice — the data MB and Spotify return for an existing recording does not change. No TTL. Manual cache bust is `rm -rf renderer/cache/`.

Cache contention isn't a concern: the publish path is `mode: restart`-style at HA (the most recent enrichment wins), so cache writes are rarely concurrent for the same key. If two writes race, last-writer wins — both writers compute the same data.

## Spotify Client Credentials token

In-memory singleton: `{ token, expiresAt }`. On call:

1. If `now < expiresAt - 60s`, return cached token.
2. Otherwise, take a refresh mutex (single in-flight promise).
3. POST to `accounts.spotify.com/api/token` with `grant_type=client_credentials` and basic auth.
4. Store new token + `expiresAt = now + (expires_in * 1000)`.
5. Release mutex; return.

No persistence to disk needed. Restart-cost is one extra API call per renderer process start (~150 ms).

## MusicBrainz politeness

- One UA header from `ha/secrets.yaml`'s `musicbrainz_user_agent`. Includes contact (operator email).
- Rate limit: 1 req/s, enforced by a small in-process semaphore (FIFO queue with 1100 ms gap).
- Cache misses are rare in steady state (composer/work entities re-used across many recordings).
- Failure modes: 503 (overloaded), 404 (not in MB), timeout. All bubble up as `null` from the enrichment module; caller falls back gracefully.

## Composer transliteration

MB returns work composer in the canonical script — Cyrillic for Shostakovich/Rachmaninoff/Tchaikovsky, Armenian for Khachaturian. For display we want a Latin form that matches what the operator sees in Spotify.

Resolution order:

1. **Match against Spotify's `artists[]`.** Spotify always uses the Latin transliteration. If MB's composer artist MBID matches one of Spotify's artist MBIDs (via `external-urls`), use Spotify's name. Cheap, no extra API call.
2. **Fetch MB artist with `inc=aliases`.** Pick the first alias with `locale: "en", primary: true`. One extra cached call per non-Latin composer (~10 in the operator's rotation, one-time).
3. **Fall back to MB's raw name.** Worst case the panel shows Cyrillic for one render; subsequent renders hit the alias cache.

Step 1 may not actually work since Spotify's API doesn't expose MBIDs. Treat step 1 as best-effort and step 2 as the reliable path.

## Pop layout (non-classical)

Today's layout puts `title` in a 72u serif top slot, `artist` in 32u mono caps, `album` in 32u sans. Three observations made this redesign worth bundling with the classical work:

1. **Work + album equally weighted is wrong.** Every mainstream music app weights track > artist > album. The current face buries the artist and gives the album equal real estate to the song. Replacing with `top: artist, big: track, bottom: album+year` matches user mental models from Spotify, Apple Music, CarPlay, etc.
2. **Symmetry with classical.** The classical layout has the same three-row anatomy (label / big / strip). Reusing the structure means one set of CSS owns both modes; the `classical` boolean only switches what populates each slot.
3. **Album+year strip is more useful than album+sans.** The release year answers "is this a recent release or a classic?" — high-signal in <5 chars. Currently shown nowhere.

Consequence: every render of a non-classical track changes typography. Worth flagging to the operator for sign-off; mitigation is the mock at `/debug/now-playing-classical-mock?i=1` which shows the new pop layout against the only pop track in today's history.

## Year selection: MB vs Spotify

MusicBrainz `recording.first-release-date` is the year the *recording entity* was first released. Accurate when MB has the original release entry catalogued; can be off by decades when MB only has a remaster (e.g. the Pollini Chopin Nocturnes ISRC resolves to a 2022 reissue's recording entity).

Spotify's `album.release_date` is the date of the *specific album version* — also unreliable for remasters (the 2024 half-speed master returns 2024).

Neither is authoritative on its own, but they fail in different directions:

- MB tends to **overshoot** when the original recording isn't catalogued (latest curator-known release wins).
- Spotify tends to **overshoot** when the user is streaming a remaster (always returns the remaster's date).

Both fail towards the more recent date. Taking `min(MB, Spotify)` reliably picks whichever source got it right. When both return the same date, the answer is correct trivially. When both are wrong, both will be wrong in similar ways — but `min` still picks the lower.

Implementation:

- `MB.first-release-date` (year only) and `Spotify.album.release_date` (year only) both go into the enriched record.
- Display year = the smaller of the two non-empty values. If only one is present, use it. If neither, hide the year row.

## Edge cases

| Case | Behaviour |
|---|---|
| Track has no `media_content_id` (Sonos source not Spotify, e.g. AirPlay raw) | enrichment skipped → existing fields drive flat layout |
| Spotify API down / 401 / 429 | enrichment returns null → flat layout from existing fields |
| MB API down / 503 | use Spotify-only fields → no role chips, no MB-side composer; if Spotify artists[] looks composer-shaped (≥2 entries, classical-shape title) treat as classical |
| ISRC not in MB at all | same as MB down for this track |
| MB recording exists, no work-rel | classical signal still positive (typed performer disambigs); composer fallback to Spotify artists[0] |
| Composer name in non-Latin script, no Spotify match | fetch artist aliases, pick `locale=en primary` |
| Composer name in non-Latin script, no en alias either | render raw MB name (rare; would mean the artist has no English alias in MB) |
| Pop track with no album.release_date | year row hidden |
| Two consecutive tracks, both miss MB | both render with Spotify-only fallbacks; second one's enrichment doesn't block on rate limit because MB calls are gated per-second |

## Out of scope

- **Composition year (Beethoven 1808, etc.).** Requires walking MB work → parent work → Wikidata Q-number → P571 inception, with poor data quality (probed Q41327 for Beethoven 5 and got "+1992-02-19" inception, clearly wrong). A hard-coded composer-work composition-year table covers the operator's actual canon but is maintenance debt. Defer.
- **Curated short forms for ensemble names** (`Berliner Philharmoniker → BPO`). The wrap-instead-of-truncate fix gets us to "long names display in full"; abbreviating is a separate aesthetic question.
- **Live composer Q-number lookup.** Same reason — Wikidata has it, but the resolution chain is fragile and adds two more API calls per non-Latin composer.
- **HA-side enrichment pipeline.** Keeping the enrichment renderer-side keeps HA's role to "publish current Sonos state", same as it already does.
- **Re-enriching on every device wake.** Cache hits are pure file reads; no need for invalidation. If MB updates a recording's metadata, the cached entry stays. Rare and not worth the complexity.

## Migration / rollout

The operator can preview every layout via the existing `/debug/now-playing-classical-mock` route before this change ships. Once the renderer code lands, the existing pop track (if any plays) draws the new pop layout immediately. Existing classical tracks already in MB cache (the 38 tracks scanned during prototyping) render the classical layout on first encounter.

There is no firmware change and no schema break for HA's publisher — old `sonos.json` payloads continue to work; renderer just adds enriched fields when they're available.
