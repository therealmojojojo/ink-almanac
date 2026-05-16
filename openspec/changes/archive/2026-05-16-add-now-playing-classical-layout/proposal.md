# Proposal: Classical-aware Now-Playing layout

## Why

The current Now-Playing face is built around the `title / artist / album` shape that pop streaming uses. Classical metadata coming through Sonos+Spotify has the same three string slots but a fundamentally different *meaning*:

- The composer (Beethoven, Chopin, Shostakovich) is the canonical identity. Spotify hides it inside the album title prefix (`"Beethoven: Symphonies …"`).
- The "artist" field is the *performer* — orchestra, conductor, soloist, often three or four names joined by semicolons. Single-line all-caps mono is hostile here.
- The track title is `Work, Op./BWV/K.: Movement`, mashed into one string. The natural hierarchy work → movement is flattened.

Today the operator's listening rotation is mostly classical (38 tracks observed in one day; 37 of 38 detected as classical via MB). The pop layout misrepresents every one of those tracks: composer buried in the album, performer crammed and truncated, work title hitting the smallest font bucket and still cropping.

A second observation while researching this: the existing pop layout sized track and album equally and put album in the big serif slot. Every mainstream music app puts the **track** as the primary display element, with artist secondary and album tertiary or hidden. The pop slot ordering needs to be corrected at the same time.

## What Changes

### Renderer

- New module `renderer/src/enrichment/`. On every Sonos input change, look up the Spotify track id via Spotify Web API (Client Credentials flow), then MusicBrainz by ISRC, then follow the work-relation for composer + canonical work title. Disk-backed cache by Spotify id, ISRC, work MBID, and artist MBID (composer alias). Cache forever — recording metadata does not change.
- Schema extension. `sonosInput` in `renderer/src/modes/schema.ts` gains optional `composer`, `work`, `movement`, `performers[]`, `first_release_year`, `classical: boolean`. The publisher (HA) keeps writing the existing fields; the renderer fills in the new ones from the enrichment cache before rendering.
- Template + CSS rewrite. `renderer/templates/now-playing/` adopts the iterated mock layout: composer in the source-strip slot (mono caps, hairline below), work in the adaptive serif slot (4-bucket size ladder by length), movement as italic serif subtitle when present, performers in a typed-chip list at the bottom (mono caps, hairline above), release year as a small faint trailing row.
- The same three-row shape ships for non-classical tracks too: artist as the top mono-caps label, track in the big serif slot, album-and-year as the bottom strip. The pre-existing flat layout (`title` huge serif, `artist` mono caps, `album` sans) is replaced.

### Configuration

- `ha/secrets.yaml` adds `spotify_client_id`, `spotify_client_secret`, and `musicbrainz_user_agent`. The `.example` template updates accordingly. The renderer reads these the same way it reads `ha_long_lived_token` today (filesystem read of `../ha/secrets.yaml`, no service required).

### Spec

- `openspec/specs/now-playing-override/spec.md` — ADD Requirement "Classical metadata enrichment", ADD Requirement "Composer-anchored layout for classical tracks", ADD Requirement "Track-anchored layout for non-classical tracks", ADD Requirement "Release year".

## Impact

- **Behaviour change.** Visible — every Now-Playing render that has a Spotify track id changes typography. Pop tracks see the album/track ordering swap. Operator must approve the new pop look.
- **Latency.** Cache miss adds ~500–800 ms (Spotify ~150 ms, MB ~600 ms across 1–3 calls at 1 req/s). First time per track only; cached forever after. Well within the 10 s activation budget.
- **External dependencies.** Spotify Web API (free, app-only token), MusicBrainz public API (free, rate-limited to 1 req/s). Both can be unreachable without breaking the face — fallback path renders the flat layout from the existing fields.
- **No firmware change.** Renderer-only.
- **Risk.** Medium. New external API surface, persistent on-disk cache, schema extension. Mitigated by: (a) all new fields optional, missing-field path renders today's flat layout; (b) cache hits are pure local file reads; (c) MB `first-release-date` cross-checked against Spotify `album.release_date` so a single-source bad year can't poison the display.
- **Testability.** The 38-track preview at `/debug/now-playing-classical-mock` already demonstrates every layout variant against today's listening. The same dataset becomes a fixture for renderer integration tests.
