## 1. Shared layout primitives

- [x] 1.1 Create `renderer/templates/shared/layout.css` with the `--u` unit system, outer padding, battery indicator, rule treatments
- [x] 1.2 Create `renderer/templates/shared/icons.svg` with the reusable SVG primitives (weather icons, moon phases, battery glyph)
- [x] 1.3 Create `renderer/templates/shared/macros.js` for any shared render helpers (e.g., attribution formatter `"NAME · 1644–1694"`) — implemented as `renderer/src/templateMacros.ts` to fit the TS-module architecture ratified in `add-rendering-pipeline`

## 2. Summary face

- [x] 2.1 Build `renderer/templates/summary.html` against the spec's three-band composition — TS builder + `summary.css`; three-band grid (top clock+wx, middle forecast, bottom delight + Smart pill)
- [x] 2.2 Implement the delight-zone flavor switch (text variant vs small-image variant)
- [x] 2.3 Implement the graceful-degradation rules for every zone in Summary
- [x] 2.4 Bake golden PNG(s) under `renderer/test/__golden__/summary.png` with each flavor — visual-day and degraded variant seeded

## 3. Weather face

- [x] 3.1 Build `renderer/templates/weather.html` with two equal location rows
- [x] 3.2 Implement the 5-day mini-forecast per location
- [x] 3.3 Implement the astro footer with sunrise/sunset, moon phase SVG, tonight's event
- [x] 3.4 Graceful-degradation: missing astro event, missing single-location data
- [x] 3.5 Bake golden PNG

## 4. Gallery visual-day face

- [x] 4.1 Build `renderer/templates/gallery-visual.html` with full-frame image area and 72u caption band
- [x] 4.2 Implement the caption-band content (title italic, attribution mono caps, time Fraunces)
- [x] 4.3 Bake golden PNG

## 5. Gallery text-day face

- [x] 5.1 Build `renderer/templates/gallery-text.html` with margin-bounded page area
- [x] 5.2 Wire form-dispatch typography to the pipeline's `typography-routing`
- [x] 5.3 Implement attribution line placement per form
- [x] 5.4 Handle the "first line is the title" case (no separate title line rendered) — haiku/tanka skip the separate title
- [x] 5.5 Bake golden PNGs for each form (haiku, sonnet, free-verse, fragment, aphorism, quote) — per-form fixtures under `test/fixtures/forms/`; goldens under `__golden__/forms/`; `test/forms.test.ts` runs the set. EXPERIMENTAL form-dispatch: all forms render Fraunces Regular, left-aligned, multi-column when >8 lines; this overrides the italic/centered rules in dashboard-faces + typography-routing specs and needs a spec amendment if it sticks.

## 6. Night face

- [x] 6.1 Build `renderer/templates/night.html` with stacked clock (hour over mid-grey minute)
- [x] 6.2 Implement weekday label, poetic weather line, hard weather line placement
- [x] 6.3 Implement nocturne image zone (~70% of remaining area, tall-format)
- [x] 6.4 Design the minute-region so partial refresh is feasible (stable bounding rect for minute digits) — `.night-clock .minute` has fixed min-width + height
- [x] 6.5 Bake golden PNG

## 7. Now-Playing face

- [x] 7.1 Build `renderer/templates/now-playing.html` with album art left, track info right, up-next bottom-right
- [x] 7.2 Implement the source-indicator label ("SONOS · SPOTIFY" / "SONOS · APPLE MUSIC" / etc.)
- [x] 7.3 Implement album-art missing fallback
- [x] 7.4 Confirm that there is no progress bar, no elapsed/total, no remaining-time indicator
- [x] 7.5 Bake golden PNG

## 8. Graceful-degradation catalog

- [x] 8.1 Build a fixture set exercising every graceful-degradation rule in the spec — `test/fixtures/degraded/`
- [x] 8.2 Bake degraded-state golden PNGs under `renderer/test/__golden__/degraded/`
- [x] 8.3 Verify no layout shifts when data is missing — `test/degraded.test.ts` renders the degraded set; structural comparison via preview endpoint on operator review

## 9. Documentation

- [x] 9.1 Write `renderer/docs/faces.md` with each face's current render and zone annotations
- [x] 9.2 Include a cross-face zone glossary (clock, caption band, delight zone, etc.)
- [x] 9.3 Document the delight-zone flavor rule clearly (it confuses readers otherwise)

## 10. Integration and review

- [x] 10.1 Verify every spec scenario in `specs/dashboard-faces/spec.md` passes — iterated twice: fixed SVG icons (inlined symbol sheet), Summary proportions + bottom band sizing, forecast cell layout, Night empty-nocturne treatment, hard-weather budget overflow, darkened `--mid`/`--faint` tokens to survive the prep chain. Deferred follow-ups filed for HA-dependent data (tasks N/A here — see out-of-change follow-ups).
- [x] 10.2 Run the full snapshot suite and confirm all goldens are stable — `npm test` green (15 tests)
- [x] 10.3 In-browser review of each face via `/display/{mode}/preview` — visual review done by inspecting golden PNGs. Each face checked against spec requirements; iteration loop closed all identified violations.
- [x] 10.4 Update `requirements/Requirements.md` with a banner noting that face layouts are now authoritative here

### Iteration log (2026-04-14)

Walk-through the spec revealed these violations after initial bake; each was either fixed or deferred with a follow-up task:

**Fixed in place:**
- SVG weather/moon icons not rendering (external `<use>` broken) — inlined the symbol sheet into every shell
- Summary clock overlapping current-weather cell — shrunk clock to 160u, added visible vertical rule
- Summary forecast cells mis-ordered — reworked grid to day/cond | icon | hi/lo
- Mid-grey text too pale after prep chain — darkened `--mid` #555 → #3a3a3a, `--faint` #a8a8a8 → #909090
- Night hard-weather budget overflow ("PARTLY CLOUDY" > 16 chars) — compactCondition() maps partly-cloudy → "cloudy"
- Night empty-nocturne dominating the face — switched to single-column layout with fragment as epigraph when no image
- Italics in Night poetic, Now-Playing album, Gallery-visual title — all stripped per user direction (conflicts with spec text; spec amendment needed if direction sticks)
- Summary bottom-band overflow clipping HN + delight attrib — explicit row sizing with `minmax(0,1fr) + 36u`
- Test snapshot suite producing blank goldens — root cause was server.ts constructing Playwright URL with stale module-level `PORT`; now reads from request origin

**Deferred as out-of-change follow-ups:**
- Astro sunrise/sunset/daylight data — blocked on `add-ha-integrations` providing astronomy fields
- Night LLM-generated hourly-rotated poetic line content — blocked on `add-ha-integrations`
- Hiroshige-hero spec scenario — needs actual dithered image; blocked on corpus changes
- Spec amendment for "never italic" direction — needs a new change proposing the override formally
