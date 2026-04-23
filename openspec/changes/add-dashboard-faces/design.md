## Context

`requirements/Mockup.html` is a working sketch for Summary and Weather at 1200×825 using the `--u` unit system. It predates several design decisions that matter here:

- Now-Playing became a full-frame override. Summary no longer carries a "Spotify/HN" combined card; instead, the bottom-right of Summary becomes a stable sidebar with indoor climate + news feed, and the bottom-left is the delight companion.
- The "no Ozymandias in italics" rule forces form-aware typography in Gallery text-day.
- Gallery's dual nature (visual vs text day) needs consistent caption treatment.
- Night mode needs a concrete layout (Mockup.html doesn't cover Night).
- Now-Playing didn't exist in the mockup.

This change takes the good patterns from Mockup.html (the `--u` scale, the three-band Summary composition, the palette discipline, the font stack) and builds six ratified faces on top.

## Goals / Non-Goals

**Goals:**
- A visual contract per face that a future contributor (or Claude) can re-render from spec without referring to Mockup.html.
- Zone composition that reads clearly at 2–3 m in kitchen lighting — the distance the frame actually gets viewed from.
- Graceful degradation so missing data never breaks layout.
- Low-chrome, high-content — every zone earns its pixels.

**Non-Goals:**
- Design evolution after initial ratification. Visual changes are entirely normal, handled by subsequent change proposals that modify this capability's requirements.
- Interactive design tools, Figma files, or any artifact outside the repo. The HTML templates are the design artifact.
- Responsive layouts. Every face is exactly 1200×825.
- Dark/light themes. The palette is fixed per rendering-pipeline.

## Decisions

### Six faces, one spec file

Rationale: the faces share conventions (padding, battery indicator, fallback rules) and read as a set. One spec file per face would duplicate the conventions and make cross-face consistency harder to audit. Requirements within the single file are grouped per face so changes still stay localized.

### Summary's sidebar is stable; Now-Playing is full-frame

Rationale: during the original design conversation, the user confirmed that Sonos playback replaces the whole frame rather than injecting a card into Summary. That simplification means Summary has no variable sub-mode; it's just one composition whose bottom bands contain indoor climate + news + delight content. News content is first-class (not a Spotify fallback) — HN is there because morning news has standalone value.

### Delight zone flavor follows pairing, not mode

The delight zone renders text when the pairing is visual-day (hero image, companion text) and renders a small image when the pairing is text-day (hero text, companion visual). Summary doesn't know or care about the flavor beyond consuming the companion content — the pairing pipeline and rendering pipeline coordinate the flavor determination.

### Gallery caption band is universal

Both visual and text days have a caption band. Rationale: consistent cues help orient — someone walking by sees "this is a Gallery view" via the caption treatment regardless of what's in the main area. Text-day can suppress the caption when it would be redundant with the attribution line, to avoid duplicated metadata.

### Night is minimum chrome

Night is the longest-displayed face (8.5 hours/day). It must feel calm — no forecast, no news, no climate. Just clock, date, one poetic line, one hard weather line, one nocturne image. This is also the cheapest face for power budget (partial refreshes possible for minute tick, low refresh rate overall).

### Now-Playing has no progress bar

Decided in design: a ticking progress bar on e-paper ghosts badly, burns partial refreshes, and provides low-value information (you know where the song is; a bar doesn't help). Track changes are the natural refresh trigger. This is a power-budget and aesthetic decision both.

### Stacked clock for Night, not digital strip

Rationale: the stacked composition (hour on one line, minute on the next in mid-grey) reads well at ambient-glance distance from bed/doorway, avoids the "digital clock radio" feel, and lets the minute refresh via a local partial redraw of only the minute region — minimizing refresh cost during the long night.

### Each face has a graceful-degradation rule

Rationale: data pipelines fail. A rendered face with gaps must look intentional, not broken. An em-dash beats a crash. The placeholders are small and typographic; the layout does not shift.

## Risks / Trade-offs

- **Layout ratification limits iteration speed.** Every visual tweak needs a spec update. Mitigation: this is the right tradeoff for a "wife factor" product — visual discipline matters more than rapid change.

- **Six faces × many graceful-degradation rules = combinatorial surface.** Easy to miss a fallback. Mitigation: the spec's graceful-degradation catalog enumerates every rule; snapshot tests can cover the degraded states explicitly.

- **The mockup used a "Spotify fallback HN" on Summary that users may miss.** Mitigation: the change explicitly documents the supersession ("Now-Playing is a full-frame override; Summary carries HN as first-class news").

- **Caption band on Gallery might feel museum-heavy.** Attribution in mono caps can read as formal. Mitigation: visual review of goldens; if it feels wrong, the caption treatment is easily adjusted via a follow-up change.

- **Form-dispatch typography can surprise when a text's form is mistagged.** Mitigation: ingestion's review step is where form gets chosen; a sonnet mistagged as "fragment" would render italic-emotive when it should be roman-dignified. Catching this is part of `build-seed-corpus`'s review discipline.

## Migration Plan

No prior templates exist. On apply:

1. Build `renderer/templates/shared/layout.css` with common conventions.
2. Build Summary first — most complex, exercises the most zones. Golden bake and visual review.
3. Build Weather, Gallery visual-day, Night, Gallery text-day (each form variant), Now-Playing in any order.
4. Bake goldens for each; the test harness from `add-rendering-pipeline` validates that future template changes don't silently drift.
5. Write `renderer/docs/faces.md` with each face rendered + annotated.

Rollback: delete the templates. The rendering pipeline still exists and could serve blank PNGs or test fixtures.

## Open Questions

1. **Delight zone image size.** For text-day flavors, how small should the companion image be? Large enough to see detail, small enough to leave room for climate + HN. A 640×380u footprint feels right. Confirm visually at golden time.

2. **Gallery caption time format.** `08:47` in Fraunces tabular vs mono. Probably Fraunces for aesthetic consistency with the clock in Summary. Defer to visual review.

3. **Now-Playing during Gallery hours.** The current rule is "music always preempts." Should there be a "don't interrupt Gallery between 14:00-16:00" override? Probably not — simpler is better. Revisit if the wife asks.

4. **Whether to show Sonos volume somewhere on Now-Playing.** Probably no — it clutters and isn't useful information for a kitchen display. Omit unless requested.

5. **The "up-next" track.** Sonos sometimes doesn't have an up-next reliably. When missing, omit the zone gracefully (don't fill with placeholder).
