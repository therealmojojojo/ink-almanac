# now-playing-override Specification — delta

## ADDED Requirements

### Requirement: Classical metadata enrichment

When the publisher writes a Sonos input that includes a Spotify `media_content_id`, the renderer SHALL enrich the input with structured metadata before persisting it. The enrichment SHALL produce these fields when sources are reachable:

- `composer` (string) — the canonical Latin form of the composer's name.
- `work` (string) — the work title minus any movement suffix.
- `movement` (string) — the movement designation, when the title contains a movement-shaped suffix.
- `performers` (list of `{ name, role }`) — performers as published by Spotify, ordered as Spotify orders them, with role labels derived from MusicBrainz artist type and disambiguation when available.
- `first_release_year` (string `YYYY`) — the smaller of MusicBrainz's `recording.first-release-date` and Spotify's `album.release_date`.
- `classical` (boolean) — true when the track is classifiable as classical.

A track is classical when any of the following holds:

- MusicBrainz returned a recording with a work-rel that resolves to a work with at least one composer relation; OR
- MusicBrainz returned typed performer disambiguations (`pianist`, `cellist`, `violinist`, `harpsichordist`, `conductor`, `soprano`, `mezzo`, `tenor`, `baritone`, `bass`, etc.) or ensemble types (`Orchestra`, `Choir`, `Group`); OR
- Spotify lists 2+ artists AND the track title matches a catalogue marker (`Op.`, `BWV`, `K.`, `RV`, `TH`, `R.`, `D.`, `L.`, `S.`, `WoO`, `Hob.`, `HWV`) or a known classical form (`Symphony`, `Concerto`, `Sonata`, `Quartet`, `Prélude`, `Étude`, `Nocturne`, `Mazurka`, `Sarabande`, `Allemande`, `Gigue`, `Mass`, `Fugue`, `Suite`, `Variations?`, `Carnival`, `Pieces`, `Songs`, `Romance`, `Lied`, `Gymnopédie`, `Gnossienne`, `Liebestraum`) or a roman/arabic-numeral movement marker after a colon.

When enrichment cannot complete (Spotify unreachable, MB unreachable and Spotify alone insufficient, no Spotify track id), the renderer SHALL persist the original publisher payload unchanged. Renders fall back to the non-classical layout populated from the existing `title`/`artist`/`album` fields.

Enrichment results SHALL be cached on disk indefinitely. Cache keys are the Spotify track id, the ISRC, the MusicBrainz work MBID, and the MusicBrainz artist MBID (for composer aliases). Recording metadata is treated as immutable; no TTL applies.

#### Scenario: Classical track is enriched on first encounter

- **WHEN** Sonos starts playing a Spotify track for which the operator has not previously seen the renderer enrich, and that track resolves via ISRC to a MusicBrainz recording with a work-rel
- **THEN** within ~800 ms of receiving the publisher payload the renderer has produced an enriched `sonos.json` with `composer`, `work`, optional `movement`, `performers[]` carrying typed roles, `first_release_year`, and `classical: true`. Subsequent encounters of the same track read from cache and complete in under 5 ms.

#### Scenario: Spotify and MusicBrainz both unreachable

- **WHEN** Sonos starts playing a track but Spotify's API and MusicBrainz are both blocked from the renderer host
- **THEN** the renderer persists the original publisher payload without `composer` / `work` / `classical` fields, and Now-Playing renders the non-classical layout using the existing `title` / `artist` / `album` fields.

### Requirement: Composer-anchored layout for classical tracks

When the renderer draws Now-Playing for a track with `classical: true`, the right column SHALL anchor the composer at top, the work in the primary serif slot, the movement (if present) below the work as italic serif, and the performers in a typed list at the bottom. Specifically:

- Composer in mono caps with wide letter-spacing, hairline rule below the line (top label slot).
- Work in Fraunces serif sized adaptively by character count: ≤14 → 48u, ≤22 → 38u, ≤34 → 32u, otherwise 26u with tighter line-height. Wraps to 2 lines naturally; non-breaking thin spaces glue tokens like "No. 8" and "C minor".
- Movement in italic Fraunces at 26u, hidden when empty.
- Performers in mono caps at 24u with optional role chip at 18u in a fixed left column. The role chip is omitted when the performer's type is `Orchestra`, `Choir`, or `Group` (the type is already in the name). Names wrap rather than ellipsise.
- Release year as a small (20u) faint trailing row below the performer list, hidden when no year is known.
- Source indicator (e.g. `SONOS · SPOTIFY`) and clock keep their existing top-corner / bottom-right corner anchors.

#### Scenario: Multi-credit chamber recording renders with typed roles

- **WHEN** the input has `composer = "Erik Satie"`, `work = "Gymnopédie No. 1"`, `movement = ""`, `performers = [{name: "Gautier Capuçon", role: "Cello"}, {name: "Jérôme Ducros", role: "Piano"}, {name: "Orchestre de chambre de Paris", role: ""}, {name: "Adrien Perruchon", role: "Cond."}]`, `first_release_year = "2020"`
- **THEN** the right column renders ERIK SATIE / Gymnopédie No. 1 / (no movement) / four performer rows with chips (`Cello | Gautier Capuçon`, `Piano | Jérôme Ducros`, `Orchestre de chambre de Paris` (no chip — wraps if needed), `Cond. | Adrien Perruchon`) / 2020. No truncation; long ensemble names wrap.

### Requirement: Track-anchored layout for non-classical tracks

When the renderer draws Now-Playing for a track with `classical: false` (or the `classical` field absent), the right column SHALL use the same three-row anatomy as the classical layout, populated as artist / track / album+year:

- Artist (from `sonos.artist` or enriched `performers[0].name`) in the top label slot, mono caps with hairline rule below.
- Track name (from `sonos.title`) in the work slot, Fraunces serif with the same adaptive size buckets as classical.
- Album with release year (from `sonos.album` plus `first_release_year` when available) in the bottom strip, mono caps with hairline rule above. Format: `ALBUM · YEAR` when both present; `ALBUM` alone when no year.

The layout SHALL match the conventional music-app hierarchy track > artist > album in visual weight. The previously-shipped flat layout (large serif title, mono-caps artist, sans album) is replaced.

#### Scenario: Pop track renders with track in the primary slot

- **WHEN** the input has `title = "Drinking Age"`, `artist = "Cameron Winter"`, `album = "Heavy Metal"`, `first_release_year = "2024"`, `classical = false`
- **THEN** the right column renders CAMERON WINTER (top label) / Drinking Age (big serif) / HEAVY METAL · 2024 (bottom strip).

### Requirement: Release year selection

When both Spotify's `album.release_date` and MusicBrainz's `recording.first-release-date` are present, the renderer SHALL use the *earlier* year. When only one is present, it SHALL use that one. When neither is present, the year row / suffix SHALL be omitted from the layout.

This rule reflects that both sources err towards more-recent dates when their underlying catalogue lacks the original release: Spotify because it returns the active album version's date, MusicBrainz because its volunteer catalogue may only have remasters. Taking the minimum favours whichever source got the original right without privileging either.

#### Scenario: Spotify reports remaster year, MB reports original

- **WHEN** Sonos plays a track whose Spotify `album.release_date` is `"2024-08-23"` (a 2024 half-speed master) and MusicBrainz's `recording.first-release-date` is `"1975"` (the original release)
- **THEN** the rendered year is `1975`.

#### Scenario: MB reports remaster year, Spotify reports original

- **WHEN** Sonos plays a track whose Spotify `album.release_date` is `"2008-09-15"` and MusicBrainz's `recording.first-release-date` is `"2022"` (because MB only catalogues a 2022 reissue of that recording entity)
- **THEN** the rendered year is `2008`.

#### Scenario: Neither source returns a year

- **WHEN** Sonos plays a track for which both `album.release_date` and MusicBrainz's `first-release-date` are absent
- **THEN** the year row in the classical layout is omitted; the album bottom strip in the non-classical layout shows the album name without a `· YEAR` suffix.
