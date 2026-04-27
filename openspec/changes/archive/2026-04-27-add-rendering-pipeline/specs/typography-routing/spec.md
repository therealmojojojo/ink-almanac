## ADDED Requirements

### Requirement: Font families

The renderer SHALL use exactly three font families, loaded from a local cache:

- **Fraunces** — variable serif with `opsz` axis, `wght` axis, and italic variants
- **IBM Plex Mono** — monospace
- **IBM Plex Sans** — sans-serif, weights 300 and 400

No other families SHALL be used in any template. Fonts SHALL be self-hosted to guarantee render reproducibility; external CDN references are for first-run fetch only.

#### Scenario: Attempted use of a fourth family

- **WHEN** a template's CSS references `font-family: Georgia`
- **THEN** a lint step in the renderer build fails with an error naming the offending file and family

### Requirement: Form-driven typography for text-day Gallery

When Gallery renders in text-day mode, the hero's `form` field SHALL select the typography treatment. All forms are set in **Fraunces Regular (upright)** at `opsz` 72, left-aligned with hanging indent on wrapped lines, and stanza breaks as whitespace. Italic is not used for body text.

Per-form default sizes (in `u`):

- `form: haiku`, `form: tanka` — 54u
- `form: aphorism` — 52u
- `form: fragment` — 48u
- `form: quote` — 44u
- `form: sonnet`, `form: free-verse`, `form: stanzaic` — 42u
- `form: prose-poem` — 36u

Sizes are starting points; the renderer MAY scale them down to fit the zone budget (see *Fit-driven sizing*).

All forms SHALL render the attribution (poet name, dates) in IBM Plex Mono small caps with letterspacing, sized 25u.

#### Scenario: All forms render upright

- **WHEN** Gallery text-day renders a hero item of any form
- **THEN** the body is typeset in Fraunces Regular at `opsz` 72, not italic

#### Scenario: Free-verse poem layout

- **WHEN** Gallery text-day renders a hero item with `form: free-verse`
- **THEN** the body is Fraunces Regular, left-aligned, hanging indent on wrapped lines, stanza breaks as whitespace

### Requirement: Fit-driven sizing

The renderer SHALL choose the body size to fit the content into the available zone without truncation, using the per-form default as the upper bound. If the content does not fit at the default size, the renderer SHALL:

1. First flow the body into additional columns, up to 3 columns, while keeping stanzas together (`break-inside: avoid`).
2. If multi-column flow is insufficient, step the size down in 2u increments until the content fits, but not below the 25u size floor.
3. If even at 25u the content does not fit, the renderer SHALL fail the render and surface a clear error; it SHALL NOT silently truncate.

Column count is governed by a per-column budget of `MAX_LINES_PER_COLUMN` lines and `MAX_CHARS_PER_COLUMN` characters declared in `typography.ts`; these are the single source of truth for flow decisions.

#### Scenario: Long poem flows to multiple columns

- **WHEN** a `free-verse` hero has 14 lines and the per-column budget is 8
- **THEN** the body flows into 2 columns at the default 42u size

#### Scenario: Very long poem steps size down

- **WHEN** a `stanzaic` hero cannot fit even at 3 columns at 42u
- **THEN** the renderer reduces the size in 2u steps until content fits, stopping at 25u

### Requirement: Language-aware treatment

Romanian text items SHALL render without any typographic change for language — the form rule above applies identically. Diacritic support (ă â î ș ț) SHALL be verified via a lint check on the Fraunces font files at build time; missing glyphs SHALL fail the build.

For bilingual items (`text_variants` present), the renderer SHALL present the original-language text by default. A future mode-level configuration MAY allow switching to a parallel or sequential presentation; this change does not commit to a specific variant-pairing layout.

#### Scenario: Romanian diacritics render

- **WHEN** Gallery text-day renders a Blaga poem containing `ț` and `ș`
- **THEN** the glyphs appear correctly in Fraunces at the specified axes

#### Scenario: Missing glyph at build

- **WHEN** the Fraunces file in the repo lacks a required diacritic glyph
- **THEN** the build step fails with an error naming the missing codepoint

### Requirement: Chrome and metadata typography

Across all modes, non-body typography SHALL follow:

- Clocks (Summary, Night): Fraunces, `opsz` 144, weight 300, tabular numerals
- Large temperatures: Fraunces, `opsz` 144, weight 300
- Small temperatures, weather labels, date strings, mode-headers, attribution: IBM Plex Mono, letterspaced, small caps
- Body copy in Summary (weather conditions, forecast details, HN titles): IBM Plex Sans 300/400

#### Scenario: Clock typography

- **WHEN** Summary renders `08:47` as the clock
- **THEN** the glyphs are Fraunces at `opsz: 144` with tabular numerals enabled

### Requirement: Size floor

No text SHALL render below 25u effective size (≈ 5mm on the physical panel), except for the battery percentage and similarly tiny chrome indicators explicitly marked in templates.

#### Scenario: Below-floor violation

- **WHEN** a template specifies `font-size: 18u` for any non-chrome zone
- **THEN** the build lint step fails with an error naming the offending selector and file

### Requirement: Palette

Every template SHALL draw from a fixed CSS palette:

- `--ink: #000` — primary text
- `--paper: #ececec` — background
- `--mid: #555` — secondary text, labels
- `--faint: #a8a8a8` — rules, separators
- No warm tints, no gradients, no other colors

#### Scenario: Out-of-palette color

- **WHEN** a template CSS references `#888`
- **THEN** the build lint step fails with an error directing the author to the nearest palette variable

### Requirement: Character budgets enforced at the renderer

Every dynamic text zone SHALL declare a character budget. The renderer enforces the budget by pre-truncating with ellipsis before handing text to the template. Templates SHALL NOT implement their own runtime wrapping or truncation.

Initial budgets (final values may be refined as templates are built):
- Spotify/HN title: 28 chars × 2 lines
- HN subtitle: 32 chars × 1 line
- Astro event title: 22 chars
- Astro event detail: 26 chars × 2 lines
- Weather condition string: 18 chars
- Night weather poetic line: 32 chars
- Haiku line: 24 chars, 3 lines max

#### Scenario: Title overruns budget

- **WHEN** Summary receives an HN title of 45 chars and the budget is 28 × 2 = 56 chars
- **THEN** the title is rendered fully; only overruns beyond the total budget truncate with an ellipsis

#### Scenario: Truncation site

- **WHEN** a Spotify title is 70 chars and the budget is 56
- **THEN** the renderer truncates to 55 chars + `…`, and the template renders the pre-truncated string without additional processing

### Requirement: Visual-gallery caption geometry

The visual-gallery caption is a fixed 72u horizontal band split as `[title 2fr] [attribution 3fr] [clock 1fr]` with 48u outer padding and 24u gaps. The caption SHALL NOT wrap or resize to fit content.

Hard caps (1 line each, no soft-wrap, no truncation):

- **Title column** (≈352u wide at 34u Fraunces): **20 characters**
- **Attribution column** (≈528u wide at 22u IBM Plex Mono, uppercase, letterspaced 0.14em): **32 characters**
- **Clock column**: reserved for "HH:MM" only

Corpus image items exceeding these caps SHALL supply two optional fields:

- `display_title`: ≤ 20 chars, shown in the caption; falls back to `title` when absent
- `display_attribution`: ≤ 32 chars, shown in the caption; when absent the renderer composes `ARTIST · YEAR` and the composed string SHALL ≤ 32 chars

If `title` exceeds 20 chars and no `display_title` is supplied, OR the composed/supplied attribution exceeds 32 chars, the item is rejected at ingestion; the renderer SHALL NOT silently truncate caption fields.

#### Scenario: Long ukiyo-e title needs display_title

- **WHEN** a Hiroshige item has `title: "Kinryūzan Temple in Asakusa at Night in Snow… from One Hundred Famous Views of Edo"` (102 chars) and no `display_title`
- **THEN** the ingestion validator rejects the item with reason `title 102 chars > 20 at gallery_title cap; supply display_title`

#### Scenario: Attribution composed from artist + year

- **WHEN** an item supplies `artist: "Hiroshige"` and `year: 1857` and no `display_attribution`
- **THEN** the renderer composes `HIROSHIGE · 1857` (16 chars) for the attribution column
