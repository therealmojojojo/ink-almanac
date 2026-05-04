# Ground the Stars cell in real ephemerides + space news

> **Status — 2026-04-30**: proposed; renderer-side wiring complete and
> typechecks clean; HA-side helper, ephemeris install, cron move, and
> freshness guard are pending. e2e smoke with real Bucharest data and a
> fabricated launch-day fixture is the gate before archiving.

## Why

The Weather face's Stars cell is the only ambient text on the panel that
has been hallucinated. Today's pipeline (`ha/scripts/generate_astro_event.sh`,
fired at 17:00) hands Claude Haiku just three inputs — moon phase, lat/lon,
date — and asks it to write something poetic about "tonight." The output
is then displayed for up to 24 h. Two real failures result:

1. **Fabrication.** With no actual sky data, the model occasionally claims
   conjunctions or visibility windows that aren't happening. There is no
   downstream check; the panel happily shows the invention until the next
   refresh. For a panel meant to reward looking at it, this is the worst
   failure mode.
2. **Staleness.** The 17:00 refresh means the cell shows yesterday's
   "tonight" line until evening, and there is no freshness guard if the
   cron silently fails — the sensor keeps serving the file forever.

A separate observation: the Stars cell's current title-plus-detail
two-element layout produces inconsistent typography vs. Sun (one element)
and Moon (one element + glyph). It also gives the model two budgets to
satisfy independently; in our experiments Haiku reliably busts the
26-char detail budget when it has a strong second beat to express.

## What Changes

### A. Renderer (already wired; verified by typecheck)

- Replace the title/detail split with a **single statement** (`.value`).
- Pick `font-size` from a 7-rung tier table (30u → 20u, sans, weight 500)
  via `pickStarsTier(text)` mirroring `summary.ts:pickFitTier`.
  - Phase 1 — largest tier ≥ 25u where the statement fits on one line.
  - Phase 2 — largest tier where wrapped lines fit the tier's mvl.
- Cell footprint stays inside today's max envelope at every tier.
- `astro_event` zone widened to maxChars 90 / maxLines 4 as backstop.
- `astro.event.detail` becomes optional in the schema (HA may keep
  publishing it; renderer ignores).

### B. HA-side data pipeline (pending)

- New Python helper `ha/scripts/generate_astro_event.py` that:
  1. Loads Skyfield + DE421 ephemeris and computes tonight's sky for
     the panel's lat/lon (sun set / next sunrise, twilight transitions,
     moon rise/set, planet visibility windows + peak alt + cardinal,
     close approaches < 5°, active meteor showers).
  2. Fetches Launch Library 2 upcoming launches (no key required).
  3. Fetches Spaceflight Now + NASASpaceflight RSS top items.
  4. Calls Haiku with the combined fact-block and a single-statement
     prompt scoped to a stargazer / space-science persona; the prompt
     forbids mentioning the moon (Moon cell already covers it).
  5. Strips a markdown fence if present, parses JSON, validates length;
     on parse failure, falls back to a deterministic Skyfield-derived
     phrase ("Jupiter high in SW until 01:00") rather than fabricated text.
  6. Writes the chosen statement to `/config/custom/inkplate/state/astro_event.txt`
     (existing path; sensor and publish-inputs flow unchanged).
- The shell wrapper `ha/scripts/generate_astro_event.sh` is replaced by
  a thin invoker; the moon-phase fallback table inside it is no longer
  load-bearing because Skyfield always provides a fact list.
- Cron moves from **17:00 → 07:00** in `ha/automations/astro_event.yaml`
  so the "tonight" line is correct for the *upcoming* night from
  breakfast onward.
- A freshness guard is added to the command-line sensor in
  `ha/integrations/command_line_sensors.yaml`: if `astro_event.txt`
  mtime > 30 h, the sensor returns empty and the renderer falls back
  to the literal "no event tonight" treatment.

### C. Persona and salience

- The prompt names the reader as a stargazer / space-science nerd and
  asks Haiku to rank for genuine interest, with explicit guidance to
  treat routine launches (Starlink, generic comm-sat) as noise and
  prioritise crewed flights, lunar/Mars/deep-space missions, novel
  vehicles, science-payload launches, and rare planetary events.
- The prompt forbids mentioning the moon (handled by the Moon cell)
  but allows moonlight as a reason to suppress faint targets.

## Capabilities

### Modified Capabilities

- **`dashboard-faces`**: Stars cell becomes a single-statement element
  with tiered font-fit; the budget table rows for `astro_event` and
  `astro_detail` are updated; the "no astronomical event tonight"
  scenario gains a sibling scenario for the freshness-guard fallback.
- **`ha-integrations`**: the Astro-data requirement is rewritten to
  describe Skyfield + Launch Library 2 + RSS as the input sources, and
  the daily refresh moves to a morning cron with a freshness guard.

## Non-goals

- Adding new HA sensors for individual planets, ISS passes, etc. The
  fact-block is computed inside the Python helper and only the final
  statement is published.
- ISS pass tracking. Skyfield can do it from a TLE, but the panel does
  not surface "pass at 22:48" — it would require a faster refresh than
  daily and add a TLE-fetch dependency. Out of scope for this change.
- A public astro API (e.g., timeanddate.com, IPGeolocation). All inputs
  are either local computation (Skyfield) or free public feeds.
- Visual changes to the Sun or Moon cells.
- Changes to `requirements/Requirements.md` (deprecated per CLAUDE.md).
