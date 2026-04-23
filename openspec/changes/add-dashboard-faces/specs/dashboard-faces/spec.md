## ADDED Requirements

### Requirement: Shared conventions across all faces

All faces SHALL adhere to shared visual conventions:

- Outer padding of 36u top/bottom and 48u left/right
- Battery percentage indicator in the top-right corner in micro-sized IBM Plex Mono (exception to the 25u size floor)
- Mode identity is implicit through content and layout; no explicit "SUMMARY" label is drawn anywhere
- Rules are 1u solid or 1u dashed `--faint` (`#a8a8a8`); section dividers are 2u solid `--ink` (`#000`)
- All zones SHALL provide a graceful-degradation treatment when required data is null or unavailable

#### Scenario: Battery indicator placement

- **WHEN** any face is rendered at 82% battery
- **THEN** the top-right corner displays a small battery glyph followed by `82%` in IBM Plex Mono

#### Scenario: Missing-data fallback

- **WHEN** a zone's required data is null at render time
- **THEN** the zone displays a minimal placeholder (empty rule, short em-dash, or blank) without breaking the layout; the renderer does NOT refuse to render

### Requirement: Zone character budgets

Every dynamic text field is assigned to a named zone with a fixed character budget. This table is the authoritative source; the renderer's `zones.ts` module and any Home Assistant template sensors that pre-truncate upstream SHALL transcribe from it literally. Any change to a budget is a spec change.

**Measurement rules (binding on all consumers of this table):**

- Lengths are measured in **extended grapheme clusters** (Unicode UAX #29). Romanian precomposed diacritics (`ă`, `â`, `î`, `ș`, `ț`) count as one character. Combining sequences count as one character per visible glyph.
- The ellipsis character is `…` (U+2026), never three dots.
- **Truncation split:** Home Assistant template sensors SHALL pre-truncate prose values at word boundaries before sending them to the renderer (pretty cut). The renderer SHALL enforce the same budget as a last-resort hard cut (may split mid-word) appending `…`. Both layers target the same numeric budget from this table.
- **Verse is never truncated.** Zones with `kind: verse` reject inputs that exceed their budget; the pairing pipeline is responsible for ensuring verse selections fit.
- **Ownership:** when a budget needs to change, edit this table first, then propagate to `zones.ts` and to HA template sensors. A build-time check in the renderer fails if `zones.ts` and this table diverge.

**Budget table:**

| zone_id         | face         | maxChars | maxLines | kind  | notes                                                |
| --------------- | ------------ | -------- | -------- | ----- | ---------------------------------------------------- |
| weather_cond    | summary      | 18       | 1        | prose | condition string for the current-weather block       |
| forecast_cond   | summary      | 14       | 1        | prose | per-day condition label in the 3-day forecast        |
| hn_title        | summary      | 28       | 2        | prose | HN title when no Sonos                               |
| hn_subtitle     | summary      | 32       | 1        | prose | HN domain/metadata line                              |
| climate_label   | summary      | 12       | 1        | prose | indoor climate label (e.g., "KITCHEN")               |
| delight_text    | summary      | 24       | 4        | verse | short text companion on visual-day                   |
| delight_attrib  | summary      | 40       | 1        | prose | mono-caps attribution under delight text or image    |
| location_name   | weather      | 16       | 1        | prose | e.g., "${PLACE_A_NAME}", "${PLACE_B_NAME}"                         |
| weather_cond_w  | weather      | 18       | 1        | prose | condition string in each location row                |
| astro_event     | weather      | 22       | 1        | prose | astronomical event title                             |
| astro_detail    | weather      | 26       | 2        | prose | astronomical event detail                            |
| gallery_title   | gallery      | 20       | 1        | prose | caption band title (display_title if present, else title) |
| gallery_attrib  | gallery      | 32       | 1        | prose | mono-caps "ARTIST · YEAR" (display_attribution if present) |
| poem_body       | gallery      | 64       | 32       | verse | text-day hero; form-specific sub-budgets below       |
| haiku_body      | gallery      | 24       | 3        | verse | haiku-form hero                                      |
| aphorism_body   | gallery      | 48       | 6        | verse | aphorism/fragment hero                               |
| quote_body      | gallery      | 56       | 10       | verse | quote-form hero                                      |
| weekday_label   | night        | 9        | 1        | prose | e.g., "WEDNESDAY"                                    |
| poetic_line     | night        | 32       | 1        | prose | LLM-generated italic line; LLM must self-limit       |
| hard_weather    | night        | 16       | 1        | prose | mono-caps temp + wind                                |
| nocturne_attrib | night        | 40       | 1        | prose | attribution under nocturne image                     |
| np_title        | now-playing  | 24       | 2        | prose | track title (Fraunces 64u)                           |
| np_artist       | now-playing  | 28       | 1        | prose | artist, mono caps                                    |
| np_album        | now-playing  | 32       | 1        | prose | album, Plex Sans                                     |
| np_source       | now-playing  | 20       | 1        | prose | e.g., "SONOS · SPOTIFY"                              |
| np_next         | now-playing  | 24       | 1        | prose | up-next track, mono caps                             |

Values are initial. They SHALL be tuned during template build against the actual rendered panel; a tuning pass SHALL occur before Phase 5 of the rendering pipeline and any changes edit this table.

#### Scenario: HA pre-truncates at word boundary

- **WHEN** an HN title is 60 graphemes and the `hn_title` budget is `maxChars: 28, maxLines: 2`
- **THEN** the HA template sensor emits a value of at most 56 graphemes ending on a word boundary, so the renderer's safety-net truncation does not activate

#### Scenario: Renderer hard-cut is last resort

- **WHEN** HA fails to pre-truncate and the renderer receives an 80-grapheme string for `hn_title`
- **THEN** the renderer hard-cuts to 55 graphemes and appends `…`, producing a 56-grapheme final value

#### Scenario: Verse too long is rejected

- **WHEN** the pairing pipeline selects a haiku whose body is 4 lines and `haiku_body` is `maxLines: 3`
- **THEN** the renderer returns 422 naming `haiku_body`; the pairing pipeline is responsible for retry or fallback selection

#### Scenario: Budget drift detected at build

- **WHEN** the renderer builds and `zones.ts` carries `maxChars: 30` for `hn_title` while this spec table carries `maxChars: 28`
- **THEN** the build fails with a message naming `hn_title`

### Requirement: Summary face layout

Summary SHALL use a three-band composition:

- **Top band (40% height)**: clock on the left (Fraunces opsz 144, size 230u, HH:MM), current-weather block on the right (large temperature, condition, H/L/rain%), separated by a 1u vertical rule
- **Middle band (3-day forecast, ~18% height)**: three equal-width cells separated by dashed rules, each cell showing day-of-week, condition icon, condition label, high/low
- **Bottom band (remaining, with 2u solid rule above)**: two columns — left (1.45fr) holds the delight zone (the pairing's companion content: small image OR short text), right (1fr) holds a sidebar with indoor climate readout on top and news feed below

The delight zone SHALL follow the pairing's flavor:
- Visual-day flavor → companion is text → delight zone renders short text (haiku, aphorism, fragment) with attribution
- Text-day flavor → companion is visual → delight zone renders a small image with caption

#### Scenario: Summary with haiku companion

- **WHEN** Summary renders on a visual-day with a haiku companion
- **THEN** the bottom-left delight zone shows the haiku in form-appropriate typography and the haiku's attribution in mono caps

#### Scenario: Summary with small-image companion

- **WHEN** Summary renders on a text-day with an Atget photograph companion
- **THEN** the bottom-left delight zone shows the image with a caption band underneath naming title, artist, and year

### Requirement: Weather face layout

Weather SHALL present two locations with equal treatment, and an astro footer.

- **Header (auto-height)**: mode-headline ("WEATHER"), date inline, time — separated by a 2u solid rule
- **Location rows (1fr, two rows)**: each row has a name + coordinates, a current-conditions block (icon + large temperature + feels-like + H/L/rain), and a 5-day mini-forecast strip. Rows are separated by a 1u dashed rule.
- **Astro footer (auto-height, above a 2u solid rule)**: three equal cells — sunrise/sunset + daylight duration, moon phase (SVG-rendered) + next full-moon date, tonight's astronomical event

Both locations are visually equivalent; neither is privileged.

#### Scenario: Weather with two locations

- **WHEN** Weather renders for "${PLACE_A_NAME}" and "${PLACE_B_NAME}"
- **THEN** both location rows are present, neither is styled as primary, the astro row is visible at the bottom

#### Scenario: No astronomical event tonight

- **WHEN** the astro event feed returns no event for tonight
- **THEN** the astro cell for events shows a short em-dash and a label "no event tonight"

### Requirement: Gallery visual-day layout

Gallery visual-day SHALL present the hero image as a full-frame figure with a minimal caption band.

- **Image area**: occupies the full frame except for a caption band at the bottom (72u tall)
- **Caption band**: title on the left in Fraunces Italic (work title), artist/medium/year in IBM Plex Mono caps letterspaced in the middle, current time on the right in Fraunces (tabular numerals)
- **No other chrome**: no forecast, no labels, no secondary content. The battery indicator remains as the universal exception

The image is pre-dithered by the rendering pipeline; this layout specifies placement only.

#### Scenario: Hiroshige hero

- **WHEN** Gallery visual-day renders with hero `hiroshige-shin-ohashi`
- **THEN** the image fills the frame above a 72u caption band showing the work's title (italic), "UTAGAWA HIROSHIGE · WOODBLOCK · 1857" in mono caps, and the current time

### Requirement: Gallery text-day layout

Gallery text-day SHALL present the hero text as a typeset page with generous margins and per-form typography (dispatched by the rendering pipeline per `typography-routing`).

- **Page margins**: ~120u on each side, ~96u top, ~72u bottom
- **Title** (above the body): Fraunces Italic at display size, centered, when the work has a distinct title; omitted when the first line IS the title (haiku, some aphorisms)
- **Body**: typeset per the form rules from `typography-routing`
- **Attribution** (below the body): IBM Plex Mono caps letterspaced, name + dates (e.g., `MATSUO BASHŌ · 1644–1694`)
- **Caption band**: same as visual-day — title / attribution / time. For text-day, this may be redundant with the attribution line; when redundant, the caption band is suppressed and the time appears in a small corner instead

#### Scenario: Ozymandias renders upright

- **WHEN** Gallery text-day renders Shelley's "Ozymandias" (`form: sonnet`)
- **THEN** the body is typeset in Fraunces Regular (upright) per `typography-routing`, the title "Ozymandias" appears above the body in Fraunces Italic display, and the attribution reads `PERCY BYSSHE SHELLEY · 1792–1822`

#### Scenario: Bashō haiku with no separate title

- **WHEN** Gallery text-day renders a haiku where the first line is the title
- **THEN** no separate title line is rendered above the body; the haiku body appears centered with its attribution below

### Requirement: Night face layout

Night SHALL present a calm, low-content composition suited to ambient night viewing.

- **Top-left (stacked clock)**: hour line over minute line, both Fraunces in IBM Plex Mono alternative, sized tall; the minute rendered in `--mid` (`#555`) so the hour dominates
- **Below clock**: weekday label in mono caps
- **Poetic weather line**: Fraunces Italic, opsz 72, ~48u, sitting under or beside the clock — content is LLM-rotated (hourly) from `add-ha-integrations`
- **Hard weather line**: mono caps small, temp + wind, below the poetic line
- **Nocturne image**: occupies roughly 70% of the remaining frame area, tall-format, pre-dithered by the pipeline

No indoor climate, no forecast, no HN, no news of any kind.

#### Scenario: Night at 02:14 with clear weather

- **WHEN** Night renders at 02:14 with "Clear, quiet night." as the poetic line
- **THEN** the stacked clock reads `02` over `14` (with `14` in mid-grey), the weekday label is present, the poetic line is rendered in italic Fraunces, the mono hard-weather line reads something like `-3° · CALM`, and the nocturne image fills the lower-right majority of the frame

### Requirement: Now-Playing face layout

Now-Playing SHALL present what is currently playing on the kitchen Sonos speaker.

- **Album art (left, ~65% width)**: full-height, pre-dithered by the pipeline
- **Right column (~35% width)**: track title (Fraunces size 64u), artist (IBM Plex Mono caps letterspaced 28u), album (IBM Plex Sans 300, 28u), source indicator (e.g., `SONOS · SPOTIFY` in mono caps 22u at the top)
- **Up-next** (at the bottom-right, small): the next track's title in mono caps 22u, label `NEXT` above it
- **NO progress bar, NO elapsed/total timestamps** — updates occur on track change only

When the Sonos entity is paused, the face MAY continue showing the current track; when idle (no current track), the face is not rendered (the schedule takes over).

#### Scenario: Now-Playing with a Spotify track

- **WHEN** Sonos is playing "Mykonos" by Fleet Foxes from *Sun Giant EP* on Spotify
- **THEN** the face shows the album art dithered on the left, "Mykonos" as Fraunces title, "FLEET FOXES" as mono caps artist, "Sun Giant EP" as Plex Sans album, "SONOS · SPOTIFY" as source tag, and the up-next track in the bottom-right

#### Scenario: Sonos pauses mid-song

- **WHEN** Sonos transitions from `playing` to `paused` during a track
- **THEN** the face is not re-rendered immediately; the current render persists; the schedule resumes only when the Sonos state becomes `idle` for longer than the configured linger (default 90s)

### Requirement: Graceful degradation catalog

Each zone SHALL have an explicit placeholder treatment for missing data. The placeholders are:

- Missing temperature → short em-dash
- Missing condition string → blank
- Missing HN items → list shows `—` per row, up to the row count
- Missing indoor climate → labels render with em-dash values
- Missing forecast day → blank cell (no structure change)
- Missing astro event → "no event tonight" label
- Missing album art → flat `--faint` rectangle with "SONOS" in mono caps overlay
- Missing poetic weather line → render just the hard weather line and the stacked clock; no italic line

#### Scenario: Summary with no HN available

- **WHEN** HN feed is unavailable at render time
- **THEN** Summary still renders with all zones present; the HN list shows two em-dashes in place of titles
