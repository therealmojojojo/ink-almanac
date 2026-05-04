# Spec delta — dashboard-faces (Stars cell)

## MODIFIED Requirements

### Requirement: Weather face layout

The astro footer's third cell (Stars) MUST render a single statement
sourced from the publisher, sized by tiered font-fit.

The `astro_event` zone budget MUST be widened to maxChars 90 / maxLines 4
to accommodate the longest statement at the tier-table floor. The
`astro_detail` zone is deprecated — vestigial, no longer consumed by
the renderer; HA may continue to publish, but it will be dropped on
final cutover.

- The Stars cell SHALL contain exactly one text element ("the
  statement") below the cell's `STARS` label. No secondary detail line.
- The statement SHALL be rendered at a font size chosen from a seven-rung
  tier table (30u, 28u, 27u, 26u, 25u, 22u, 20u; sans, weight 500).
- The picker SHALL pick the largest tier ≥ 25u where the statement fits
  on a single line (Phase 1). When no tier ≥ 25u accommodates the
  statement unwrapped, the picker SHALL pick the largest tier where
  wrapped lines fit the tier's max-visual-lines (Phase 2). 25u is the
  floor matching the Moon cell; sub-floor tiers (22u, 20u) are reached
  only on chatty statements.
- The Stars cell footprint SHALL NOT exceed the cell's existing fixed
  envelope at any tier choice.
- The Moon cell remains unchanged. The Stars statement SHALL NOT
  mention the moon (the Moon cell already conveys phase + glyph).

#### Scenario: Stars cell renders Jupiter visibility

- **WHEN** the Stars publisher emits "Jupiter high in SW until 01:00"
- **THEN** the cell renders the statement on one line at 30u (T1) sans
  weight 500, and no detail line is emitted

#### Scenario: Stars cell renders an Artemis-launch headline

- **WHEN** the Stars publisher emits "Artemis IV launches tomorrow — first crewed lunar landing since 1972"
- **THEN** the cell renders the statement at 25u (T5) sans weight 500 with the text wrapped to three lines, fitting inside the cell's existing footprint

### Requirement: Astro event freshness guard

The Stars publisher (HA-side) MUST refuse to surface stale text. When
the upstream state file backing `sensor.astro_event_tonight` has an
mtime older than 30 hours, the sensor SHALL return an empty string
and the cell SHALL render the literal "no event tonight" treatment.

#### Scenario: Stale astro_event.txt suppressed

- **WHEN** `astro_event.txt` was last written 36 hours ago and the
  cron has not since written a fresh value
- **THEN** `sensor.astro_event_tonight` reports an empty string and
  the Stars cell renders "no event tonight" instead of the stale text

## REMOVED Requirements

### Requirement: Stars cell title-plus-detail layout

**Reason:** the title/detail split is replaced by a single statement
with tiered font-fit (see modified "Weather face layout" requirement
above). This requirement was implicit in the prior layout description;
it is removed for clarity.

**Migration:** publishers continue to write `astro.event.title`; the
`astro.event.detail` field becomes optional in the schema and
deprecated in the budget table. No device-side migration; the device
reads PNGs only.
