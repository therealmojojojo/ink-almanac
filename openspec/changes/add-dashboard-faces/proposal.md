## Why

The rendering pipeline defines how PNGs are produced; it does not define what the dashboard actually looks like. Each of the six modes (Summary, Weather, Gallery visual-day, Gallery text-day, Night, Now-Playing) needs a ratified visual layout: which zones exist, what they contain, where they sit, what they say when data is absent. Without this contract, every template edit is a negotiation about intent rather than implementation.

This change ratifies the visual design of each face: grid structure, zone composition, hierarchy of information, graceful degradation when data is missing. The existing `requirements/Mockup.html` is a working sketch of Summary and Weather; this change takes the good ideas forward, adjusts them where other design decisions (Now-Playing as full-frame, roman-default typography for long poems, etc.) force an update, and completes the set.

## What Changes

- Ratify the visual layout of each mode as a set of zones with clear roles, sizes expressed in `--u` units, and content rules.
- Resolve the Summary "Spotify zone" question: Now-Playing is a full-frame override, so Summary no longer carries a Spotify card. The zone is repurposed for the curated delight content (the pairing's companion) and an indoor-climate readout.
- Specify the Gallery caption band (title, attribution, time) that appears on both visual and text days.
- Specify the Night mode's stacked-clock treatment, the poetic weather line placement, and the nocturne image area.
- Specify the Now-Playing layout (album art, track/artist, source indicator, no progress bar).
- Specify graceful-degradation rules: when HA returns null for a field, what does the zone show?
- Specify the cross-mode conventions: header/footer bands (if any), date-time placement, mode identity cues.
- Implement each face as an HTML template under `renderer/templates/`, conformant with the agreed layout.

## Capabilities

### New Capabilities

- `dashboard-faces`: The ratified visual layout of each mode. One spec file covers all six faces as parallel requirements, because they share conventions and read together.

### Modified Capabilities

None. The templates consume `rendering-pipeline` and `typography-routing` but do not alter them.

## Impact

- **New templates**: `renderer/templates/summary.html`, `weather.html`, `gallery-visual.html`, `gallery-text.html`, `night.html`, `now-playing.html`, plus `renderer/templates/shared/layout.css`.
- **Snapshot goldens**: seven golden PNGs under `renderer/test/__golden__/` (six modes plus a Gallery text-day variant set by form).
- **Documentation**: `renderer/docs/faces.md` presenting each face as a rendered image with zone annotations — useful for reviewing intent without reading CSS.
- **No HA wiring**: templates consume typed inputs as defined by `add-rendering-pipeline`. Data production is `add-ha-integrations`' job.
- **Supersedes**: the visual direction in `requirements/Mockup.html`. Where they disagree, this change wins.
