# Faces

The six rendered faces. Each is specified in
`openspec/specs/dashboard-faces/spec.md`; this document is the render-annotated
reader's guide.

## Zone glossary (cross-face)

| Zone | Appears in | Description |
| ---- | ---------- | ----------- |
| **Clock** | Summary, Night, Weather (small), Gallery (caption) | Current time, Fraunces tabular numerals. 230u on Summary, 260u stacked on Night. |
| **Current weather** | Summary, Weather | Temperature, condition, H/L numbers. |
| **3-day forecast (Summary)** | Summary middle band | Day, condition, icon, H/L for the next three days. |
| **5-day mini-forecast (Weather)** | Weather location row | Compact strip of day/icon/H/L. |
| **Delight zone** | Summary bottom-left | Follows pairing flavor — *text* when the hero is visual, *small image* when the hero is text. See below. |
| **Climate readout** | Summary sidebar top | Indoor temperature + humidity. Label in mono caps (e.g. "KITCHEN"). |
| **HN feed** | Summary sidebar bottom | Top HN items as title + subtitle pairs. First-class news, not a Spotify fallback. |
| **Caption band** | Gallery visual, Gallery text | Title / attribution / time strip. 72u tall on visual; corner time on text. |
| **Hero** | Gallery | The main attraction — image on visual-day, typeset text on text-day. |
| **Attribution line** | Gallery, Night (nocturne) | Mono caps `NAME · DATES · MEDIUM`. |
| **Stacked clock** | Night | Hour line over mid-grey minute line. Minute region has a stable bounding rect for partial refresh. |
| **Poetic line** | Night | Fraunces italic, hourly-rotated LLM-generated weather flavor. |
| **Hard weather line** | Night | Mono caps temp + wind. |
| **Nocturne** | Night | Tall-format image, ~70% of remaining area. |
| **Album art** | Now-Playing | Full-height left ~65%. |
| **Source indicator** | Now-Playing | `SONOS · SPOTIFY`-style label. Top-right of the text column. |
| **Up-next** | Now-Playing | Bottom-right of the text column. Omitted if Sonos has no up-next. |
| **Battery indicator** | All faces | Top-right corner. Exception to the 25u size floor. |

## Delight-zone flavor rule (important — this confuses readers)

Every pairing has exactly one *hero* (visual OR text) and one *companion*
(the other flavor). The Summary delight zone renders **the companion, not the
hero**. So:

- **Visual-day hero** → Summary delight zone renders *text* (the small
  companion poem, quote, aphorism).
- **Text-day hero** → Summary delight zone renders a *small image* (the
  companion painting, photograph).

The Gallery face, meanwhile, always renders the *hero*. Summary and Gallery
therefore show complementary content on any given day: if Gallery is the
Hiroshige woodblock, Summary's delight zone is the short haiku pairing; if
Gallery is Shelley's "Ozymandias," Summary's delight zone is an Atget
photograph.

## Summary

Three bands:

1. **Top (40% height)** — clock + current weather. 2u black rule divides the
   band from the rest.
2. **Middle (~18%)** — three equal cells for the next three forecast days,
   separated by dashed `--faint` rules.
3. **Bottom** — delight companion (left, 1.45fr) and sidebar (right, 1fr).
   Sidebar stacks indoor-climate readout on top, HN feed below.

Graceful-degradation: all zones fall back to `—` or a blank rule when data is
null. See `test/fixtures/degraded/` + `__golden__/degraded/summary.png`.

## Weather

Header (`WEATHER · date · time`) with 2u bottom rule. Two equal location rows,
each containing: name + coords, current block (icon + temperature + condition),
5-day mini-forecast strip. Dashed rule between rows. Astro footer with 2u top
rule: sun (sunrise/sunset/daylight), moon (phase SVG + label), tonight's event.

Neither location is styled as primary. Astro event missing → "no event tonight"
label with em-dash.

## Gallery visual-day

Full-frame image area above a 72u caption band. Caption: italic Fraunces title
(left), mono-caps attribution (centre), Fraunces time (right). No other chrome.

The image is pre-dithered by the rendering pipeline; Gallery visual is the
canonical dithered face.

## Gallery text-day

Margin-bounded page (120u side / 96u top / 72u bottom). Title (Fraunces Italic
display) only when the work has a distinct title; omitted for haiku / tanka
where the first line *is* the title. Body typeset per `typography-routing`:

- `haiku`, `tanka` → Fraunces Italic 54u, centered
- `sonnet`, `free-verse`, `stanzaic`, `fragment`, `prose-poem` → per form rule
  ("no Ozymandias in italics")
- `aphorism` → Fraunces Italic 52u centered
- `quote` → Fraunces Regular 44u left

Attribution (mono caps) sits below the body. Time appears in a small
bottom-right corner; the full caption band is suppressed when redundant.

## Night

The longest-displayed face (8.5 h/day) — minimum chrome. Stacked clock (hour
260u black, minute 260u `--mid`) dominates the left. Weekday in mono caps,
poetic Fraunces-italic weather line, mono-caps hard weather line beneath.
Nocturne image occupies the right column — tall-format, ~70% of the remaining
frame area.

Minute region has a fixed bounding rect (width 300u, height 220u) so firmware
can do a partial refresh of just the minute digits on the Night minute-tick.

## Now-Playing

Full-frame override — no timer cadence here; track change drives the refresh.
Album art (left, ~780px / 65%). Text column (right): source indicator at top
(`SONOS · SPOTIFY`), title / artist / album in the middle, up-next at bottom.

**No progress bar.** **No elapsed/total timestamps.** Track changes are the
only refresh trigger. Missing album art falls back to a `--faint` rectangle
with "SONOS" in mono caps.

## Graceful-degradation catalog

See the spec for the authoritative list. Encoded in the templates via
`placeholder-dash` class + `orDash()` helper + conditional blocks. Tested via
`test/degraded.test.ts` + `__golden__/degraded/`.

| Zone | Missing-data treatment |
| ---- | ---------------------- |
| Temperature | Em-dash (`—`) |
| Condition string | Blank |
| HN items | Per-row em-dashes up to expected row count |
| Indoor climate | Label + em-dash values |
| Forecast day | Blank cell, layout preserved |
| Astro event | "no event tonight" label |
| Album art | `--faint` rectangle + "SONOS" mono-caps overlay |
| Poetic weather line | Omitted entirely (clock + hard line still render) |
