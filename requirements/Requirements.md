# Inkplate 10 Kitchen Fridge Dashboard — Requirements

> **Note (2026-04-14):** Face layouts (Summary, Weather, Gallery visual/text,
> Night, Now-Playing) are now authoritative in
> [`openspec/specs/dashboard-faces/spec.md`](../openspec/changes/add-dashboard-faces/specs/dashboard-faces/spec.md)
> (pre-archive location). The zone character-budget table there is the single
> source of truth; `renderer/src/zones.ts` transcribes it and the build fails
> on divergence. This document remains for background, scope, and domain
> context — layout disagreements resolve to the spec file.

A fridge-mounted e-paper picture frame with four modes, selected automatically by time of day. Each mode has a distinct register — utility, depth, beauty, quiet — matching how the kitchen is actually used through the day. A daily curated pairing gives the device its soul: one piece of visual art paired with one piece of writing, chosen by Claude each morning, shown in complementary positions on two modes so the dashboard functions as a small daily exhibition.

---

## Hardware

All purchased:

- **Inkplate 10** — 9.7" greyscale e-paper, 1200×825, 3-bit (8 levels), ESP32, built-in CC/CV lithium charger, onboard RTC with coin-cell backup, easyC (Qwiic-compatible) connector
- **5000mAh Li-Po battery** from Soldered, JST-PH pre-wired
- **LSM6DSO 6-DoF IMU breakout (easyC)** — hardware tap, double-tap, and FSM for custom gestures
- **PIR motion sensor breakout (easyC)**
- **Qwiic/easyC cables** for sensor chaining
- **Round USB-C panel-mount extension** for in-place charging

To source:

- Picture frame (IKEA RÖDALM or equivalent, ≥25mm interior depth)
- 3mm plywood/hardboard backing panel
- 6× N42 nickel-plated neodymium disc magnets, 15–20mm × 3mm
- E6000 adhesive, double-sided foam tape, small screws
- 9mm and 11–12mm drill bits for PIR lens and USB-C panel-mount holes

---

## Four modes

### 1. Summary — morning utility

- Clock (digital, HH:MM, 1-min partial refresh)
- Current weather (temp + condition + H/L + rain%)
- 3-day forecast
- Indoor climate (temp + humidity)
- Daily delight zone — the companion to Gallery's hero (see curation pipeline)
- Now Playing → HN top 2 fallback when Spotify idle
- Small battery % indicator, top-right

### 2. Weather — on-demand depth

- Two locations, equal treatment: **${PLACE_A_NAME}** (home, 95m) and **${PLACE_B_NAME}** (mountains, 900m)
- Each: current temp + condition + feels-like + H/L + rain, plus 5-day forecast
- Astro widget: sunrise/sunset + daylight duration · moon phase (SVG-rendered) + next full moon · tonight's astronomical event (meteor showers, ISS passes, planetary conjunctions, eclipses)

### 3. Gallery — daytime ambient, two faces

**Visual day**: full-frame b&w image (lithograph, etching, photograph, woodblock, chiaroscuro painting). Minimal caption band: title (italic serif), artist/medium/year (mono caps), time.

**Text day**: full-frame typeset poem or quote. Generous page margins (~120u). Fraunces italic ~48u with opsz 72 (literary optical size). Em-dash flourish opening. Stanza breaks as whitespace. Same caption band as visual day.

Both faces share the same aesthetic register. Selection is mood-driven, not mechanical — approximately 60% visual, 40% text over time.

### 4. Night — quiet hours

- Stacked monospace clock: hour line over minute line (minute rendered mid-grey so hour dominates)
- Weekday label (mono caps)
- Poetic weather line in italic serif ("Rain on the windows." / "Clear, quiet night." / "Snow by morning.") — LLM-generated from current conditions, rotates hourly
- Hard weather data in mono caps below (temp, wind)
- Nocturne art piece taking ~70% of frame, tall format
- Separate nocturne pool — does not participate in the daily pairing

---

## Schedule

```
06:30 – 10:00   Summary
10:00 – 22:00   Gallery
22:00 – 06:30   Night
Any time       → single tap peeks Weather for 5 min, auto-reverts
```

## Interaction

- **PIR motion** → wake + refresh current scheduled mode. 5-minute cooldown between PIR-triggered wakes.
- **Single tap** (LSM6DSO) → override to Weather for 5 min, then auto-revert to schedule.
- **Double tap** (LSM6DSO) → toggle between Summary and Gallery; override persists until next scheduled transition.
- **Gyroscope door filter** → suppress tap events during and for 2s after detected fridge-door rotation.
- No physical buttons on the frame.

---

## Daily curation pipeline

### The concept

Gallery is not a rotating image. It is one half of a **daily curated pairing**. Visual day: Gallery shows an image, Summary's delight shows a thematically linked short text. Text day: Gallery shows a full-frame poem, Summary's delight shows a thematically linked small visual. The two dashboards always carry complementary content, never redundant — Summary teases, Gallery reveals.

### Corpus

Two pools in Home Assistant's media folder:

- `/corpus/images/` — visual works
- `/corpus/texts/` — poems, quotes, haiku, aphorisms

Each item has a YAML sidecar with metadata:

```yaml
# images/hiroshige_shin_ohashi.yaml
id: hiroshige_shin_ohashi
title: "Sudden Shower over Shin-Ōhashi Bridge"
artist: "Utagawa Hiroshige"
year: 1857
medium: woodblock print
themes: [rain, urgency, city, movement, weather]
mood: [kinetic, caught-off-guard]
era: edo-japan
language: null
source: met_open_access
source_url: "..."
file: hiroshige_shin_ohashi.jpg
```

```yaml
# texts/basho_old_pond.yaml
id: basho_old_pond
title: "Old Pond"
author: "Matsuo Bashō"
year: 1686
form: haiku
language: [en, ja]
text_en: |
  An old silent pond—
  a frog jumps into the pond,
  splash! Silence again.
themes: [stillness, rupture, attention]
mood: [contemplative, surprised]
era: edo-japan
```

Language scope: **English + Romanian**, occasionally bilingual pairings. Fraunces supports Romanian diacritics (ă â î ș ț) — verify on actual panel before committing Romanian texts.

### Daily automation (06:25)

Single Claude API call per day. Input: date, day-of-week, season, weather forecast summary, last 7 days' pairings (for novelty), and full corpus metadata. Output: structured JSON choosing flavor + hero + companion + rationale.

```
Prompt skeleton:

Today is {date}. Season: {season}. Weather: {forecast_summary}.
Recent pairings (avoid thematic repetition): {last_7_days}.

Choose today's pairing from these pools.
[IMAGES]: {list of image metadata}
[TEXTS]: {list of text metadata}

Decide:
1. flavor: "visual" (Gallery shows image, Summary shows text companion)
         | "text"   (Gallery shows poem, Summary shows visual companion)
2. hero_id: the work that fills Gallery at full size
3. companion_id: the linked work on the other side
4. rationale: one sentence on why this pairing, for logs

The companion should resonate with the hero — echoing theme, mood, era,
or some oblique conceptual link — without restating it. Avoid literal
illustration. Favor pairings that reward attention.

Return JSON only.
```

Response is cached and rendered into two files:

- `today_gallery.png` — 1200×825 at appropriate treatment (image dithered, or poem typeset via headless browser / PIL)
- `today_delight.png` — ~640×380u at the delight zone footprint

Dashboard fetches both on 06:30 wake.

### Failure modes

- **API unavailable** → fallback to pre-generated queue (automation maintains a week-ahead buffer)
- **Malformed response** → retry once, then fallback
- **Hero or companion not found** → treated as malformed
- **Dithering produces unreadable image** → pre-flight check, fallback to next-in-queue

---

## What works on e-paper

The Inkplate 10 is 3-bit greyscale. Media that were born monochrome render beautifully; color media reduced to greyscale often don't. The corpus should lean into native monochrome work.

### Strong

- **Etchings and engravings** — Dürer, Rembrandt (etchings, not oils), Piranesi, Goya, Hogarth, Blake, Käthe Kollwitz
- **Drawings** — Leonardo notebooks, Michelangelo chalk studies, Rembrandt pen-and-wash, silverpoint
- **Woodblock prints** — Hiroshige, Hokusai, Utamaro
- **Pre-color and mid-century b&w photography** — Atget, Cameron, Nadar, FSA photographers, Capa
- **Lithography** — Daumier, Toulouse-Lautrec, Kollwitz
- **Chiaroscuro painting** — Caravaggio, Zurbarán, Georges de La Tour, early Rembrandt portraits
- **Ink wash painting** — Song Dynasty landscapes, Sesshū, Hasegawa Tōhaku

### Weak — exclude from corpus

- Renaissance oil painting (Raphael, Titian, Botticelli) — meaning carried by color
- Impressionism — dependent on color vibration
- Most modern color painting
- Color photography (Eggleston, Shore)

Run a six-image dither test (one from each strong/weak category) at 1200×825 with Floyd-Steinberg before committing corpus direction.

---

## Legal sourcing

### Tier 1 — primary corpus sources, public domain

- **Library of Congress Prints & Photographs** (`loc.gov/pictures`) — FSA archive (Lange, Evans, Rothstein, Post Wolcott, Shahn, Delano) permanently PD as US federal employees. 50+ megapixel TIFFs.
- **Rijksmuseum Studio** — 700,000+ works CC0/PD. Strong in prints and 19th-century photography.
- **The Met Open Access** — 490,000+ CC0 objects. Cameron, Nadar, Atget, Stieglitz.
- **Gallica (BnF)** — Atget's Paris archive, French 19th-century photography.

### Tier 2

- Smithsonian Open Access, Europeana, Wikimedia Commons, Internet Archive, National Gallery of Art (Washington), George Eastman Museum.

### Recently entered EU public domain

**Robert Capa** (d. 1954) — PD since January 2025. Spanish Civil War, Normandy, mid-century photojournalism.

### Personal library tier

Photographers still copyrighted (Cartier-Bresson, Koudelka, Man Ray, Kertész, Brassaï, Erwitt, Doisneau, Salgado, Ansel Adams) cannot enter the main corpus. They may be included as a **personal library tier** — scanned from books you personally own, stored locally, tagged `source: personal_library` with book citation. This is permitted under EU private-copying exception (Romania Art. 34 Legea 8/1996) for a private device that never distributes or displays publicly.

Scanning options in Bucharest: Scan-Expert, Grafoprint, CopyRo (Zeutschel overhead, non-destructive).

---

## Romanian and bilingual material

Poets for the text pool:

- **Lucian Blaga** — philosophical lyric
- **Tudor Arghezi** — dense, physical
- **Nichita Stănescu** — inventive, tender, slightly surreal
- **Marin Sorescu** — deadpan, funny, serious underneath
- **Mircea Cărtărescu** — prose-poetic
- **Ana Blandiana** — lyrical, politically charged

Visual artists for corpus (check PD status per item):

- **Constantin Brâncuși** photographs of his own sculptures — PD in France from 2028
- **Nicolae Grigorescu** (d. 1907) — PD; some works render in greyscale
- Romanian 19th-century photography via Biblioteca Națională a României

Verify Fraunces italic at 48u renders all Romanian diacritics cleanly on the actual panel before committing Romanian poems to the pool.

---

## Seed corpus plan

**~60 images:**

- 20 FSA photographs (LoC) — Lange, Evans, Post Wolcott, Rothstein
- 10 Atget Paris (Gallica)
- 5 Capa mid-century (Wikimedia, post-2025 PD)
- 5 Cameron / Nadar portraits (Met)
- 5 Hiroshige / Hokusai woodblocks (Met, Rijksmuseum)
- 5 Rembrandt / Dürer etchings (Rijksmuseum, Met)
- 5 Caravaggio / de La Tour chiaroscuro (Met)
- 5 personal library (Cartier-Bresson, Koudelka, Man Ray, Erwitt — scanned from owned books)

**~60 texts:**

- 15 haiku / tanka (Bashō, Issa, Buson)
- 10 Romanian poems (Blaga, Arghezi, Stănescu, Sorescu, Blandiana)
- 10 English/American poems (Dickinson, Whitman, Auden, Thomas, Szymborska-in-translation, Mary Oliver)
- 10 quotes / aphorisms (Beckett, Kafka, Lispector, Borges, Cioran)
- 10 short prose fragments
- 5 Eastern wisdom texts (Rumi, Zhuangzi, Dōgen)

Curate the first seed together as a weekend project rather than programmatically. The pool should feel like yours.

---

## Example pairings (reference shape)

**Mon · absurd humor · text day** — Urmuz, *Pâlnia și Stamate* (Gallery) + Picabia mechanical diagram (Summary). Romanian proto-Dada meets its French visual cousin.

**Tue · great photographers · visual day** — Julia Margaret Cameron, *Pomona* (Gallery) + Lispector fragment on mystery (Summary). Quiet sovereignty across centuries.

**Wed · love · text day** — Nichita Stănescu, *Poem* bilingual (Gallery) + Atget windowsill from Gallica (Summary). Small domestic devotions.

**Thu · tragic events · visual day** — Dorothea Lange, *Migrant Mother* (Gallery) + Auden, *Musée des Beaux Arts* (Summary). Suffering next to ordinary time.

**Fri · great personalities · visual day** — Atget, *Rue des Ursins* dawn (Gallery) + Beckett, "Fail better" (Summary). Stubborn unrewarded looking.

**Sat · absurd, funny · text day** — Sorescu, *Shakespeare* bilingual (Gallery) + Daumier caricature from Gallica (Summary). Creation as a tidy affair, laughed at.

**Sun · midsummer · visual day** — Käsebier, *The Manger* (Gallery) + Dylan Thomas, closing lines of *Fern Hill* (Summary). Childhood observed from inside its leaving.

---

## Typography

Three families only:

- **Fraunces** (variable serif, opsz 144 for large numerals, opsz 72 for literary text, italic for expressive copy) — clocks, temperatures, delight content, poem typesetting, captions
- **IBM Plex Mono** — all labels, chrome, date strings, Night-mode clock, secondary data
- **IBM Plex Sans** (300/400) — body copy, HN titles, weather details

Minimum readable font size: **25u** (≈ 5mm on-panel). Exception: close-range chrome (battery %, tiny timestamps).

## Palette

Pure black `#000` ink. Neutral paper `#ececec`. Mid-grey `#555` for secondary text. Light grey `#a8a8a8` for rules. No warm tints, no gradients — match 3-bit greyscale panel rendering honestly.

## Content producer contract

Every dynamic text field has a documented character budget per line and per zone. **Home Assistant truncates; the renderer draws literally.** No runtime wrapping. Long strings are ellipsis-cut at the producer.

Indicative budgets (finalize during build):

- Spotify/HN title: ≤28 chars × 2 lines
- HN subtitle: ≤32 chars × 1 line
- Astro event title: ≤22 chars
- Astro event detail: ≤26 chars × 2 lines
- Weather condition string: ≤18 chars
- Night weather poetic line: ≤32 chars
- Haiku: ≤3 lines × ≤24 chars

---

## Power budget

**Target: 6–8 weeks** between charges on the 5000mAh cell.

- Gallery (12 hours/day, cheapest) — one image per day, clock caption only on PIR wake
- Night (8.5 hours/day, also cheap) — minute partial refreshes, no data fetching
- Summary (3.5 hours/day, expensive mode but short window)
- Weather — only reached on-demand

Cooldowns: PIR 5-min. Scheduled wakes every 15 min during active hours (06:30–23:00). Overnight 23:00–06:30 deep sleep, PIR wake preserved.

---

## Rendering approach

**Hybrid per zone:**

- Utility zones (clocks, weather data, climate, forecast, astro widget) → native ESPHome lambda drawing with explicit coordinates
- Image zones (Summary delight, Gallery visual-day, Gallery text-day, Night nocturne) → server-rendered PNG via HA automation, fetched on wake

Data updates stay fast and local; image-heavy content benefits from real dithering done off-device.

---

## Required ESPHome components

- Mainline Inkplate platform
- LSM6DS driver, INT pin wired to wake-capable GPIO (hardware wake-on-tap, not polling)
- PIR binary sensor on a separate wake-capable GPIO
- Native API connection to HA
- Local RTC + daily NTP sync
- OTA firmware updates

## Required HA pieces

- Template sensors per zone, pre-formatted with character budgets honored
- Automation: low-battery phone notification at <20%
- Automation: daily pairing generation at 06:25 (Claude API call, render two PNGs)
- Automation: nocturne image pool rotation for Night mode
- Automation: hourly poetic weather line generation via LLM
- HN REST sensor (top stories, refresh every 30 min)
- Secondary weather location for ${PLACE_B_NAME}
- Moon phase + astronomical event data source (ephemeris or in-the-sky.org)

---

## Physical build

1. Remove cardboard back, replace with 3mm plywood
2. Cut mat to expose 9.7" active area with even border
3. Drill 9mm hole for PIR lens (bottom-right or bottom-center)
4. Drill 11–12mm hole in bottom edge for USB-C panel mount
5. Drill screw holes for magnet positioning (4 corners + 2 mid-edges)
6. Mount Inkplate centered behind the mat
7. Battery flat against plywood with foam tape
8. LSM6DSO glued to inside back, orientation aligned to frame plane
9. PIR lens through front plastic hole
10. easyC daisy chain: Inkplate → LSM6DSO → PIR
11. USB-C panel mount routed to Inkplate port
12. 6× N42 magnets glued with E6000, distributed away from center
13. Cure 24–48 hours before testing weight

Keep magnets away from children during assembly. Verify battery polarity. Don't expose assembled dashboard to >60°C.

---

## Acceptance criteria

- Mounts cleanly on fridge, no slipping over 30 days
- Battery lasts 6+ weeks under normal use
- Clock accurate within 2 min while awake
- Weather and climate current within 30 min idle, within 5s on PIR wake
- Spotify updates within 60s awake; HN fallback engages within 2 min of Spotify idle
- Tap detection <5% false positive rate from door operations
- Schedule transitions happen cleanly at boundaries
- Mode override (double-tap) persists across deep sleep until next scheduled transition
- Daily pairing generated reliably at 06:25; both files cached by 06:30 wake
- Visual days: Gallery image dithers cleanly; Summary delight text matches theme
- Text days: Gallery typesets correctly (diacritics included); Summary delight visual matches theme
- Claude API failure handled via fallback queue; dashboard never shows missing content
- Astro moon phase matches real sky within 1 day
- Readable from 2–3m in normal kitchen lighting
- Every corpus item has verified PD status or is tagged `source: personal_library` with book citation
- Romanian diacritics render cleanly at 48u italic Fraunces on the actual panel (or acceptable fallback identified)
- Looks intentional, not hobbyist

---

## Build phases

**Phase 1 — Mode 1 core (weekend 1)**
Hardware in frame. ESPHome flashed. Summary showing clock, weather, climate. PIR wake working. Battery indicator live.

**Phase 2 — Mode 1 complete (weekend 2)**
Spotify now-playing. HN fallback. LSM6DSO tap detection via INT pin. Delight zone renders placeholder image.

**Phase 3 — Modes 2 + 3 (weekend 3)**
${PLACE_B_NAME} added to HA. Astro widget (moon SVG + event feed). Visual-day Gallery with pre-curated image rotation. Schedule-driven mode switching. Single-tap Weather peek with 5-min auto-revert.

**Phase 4 — Night mode + polish (week 4+)**
Night mode with monospace stacked clock. Poetic weather line LLM automation. Nocturne image pool. Double-tap override toggle. Battery measurement.

**Phase 5 — Curation pipeline**
Seed corpus (~60 images + ~60 texts) curated and tagged. HA automation calling Claude API and rendering both daily files. Text-day Gallery treatment. Summary delight zone handling both text and image companions. Six-image dither test validates corpus media assumptions.

---

## Open questions

1. LSM6DSO INT pin — which Inkplate 10 GPIO is free and wake-capable?
2. HA automation runtime preference (Node-RED vs AppDaemon vs shell_command + Python)?
3. Astronomy data source: `ha-moonraker`, in-the-sky.org scrape, or local ephemeris?
4. Gallery image source curation: manual folder, or connected to an API (MET Object ID rotation)?
5. ${PLACE_B_NAME} weather data: does OpenWeather / MET.no cover it accurately at 900m, or need a local station?
6. Which LLM runs Night poetic weather line generation — local (Ollama) or cloud?
7. Headless rendering stack for text-day Gallery — Puppeteer on HA host, or PIL + Pillow server-side?
8. Seed corpus: pick first 60 × 60 yourself, or have Claude propose for review and trim?
9. Verify Fraunces Romanian diacritic rendering at 48u italic on actual panel before committing RO texts.
10. How explicitly should the two dashboards signal their pairing? Silent link (user discovers), small micro-label, or visible metadata?
11. Which scanning workflow for personal-library tier? (Scan-Expert, Grafoprint, CopyRo Zeutschel)
12. Floyd-Steinberg parameters — what contrast boost makes old b&w photography look printed rather than low-resolution?
13. Run six-image dither test before committing corpus guidelines.
14. Should personal-library tier be visually distinguished in caption? (E.g., "from *Exiles* · home library")
