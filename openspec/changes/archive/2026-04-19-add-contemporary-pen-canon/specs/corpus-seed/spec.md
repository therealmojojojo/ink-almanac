# corpus-seed — delta for add-contemporary-pen-canon

## ADDED Requirements

### Requirement: Pen-first non-photograph spine

The non-photograph image pool SHALL be weighted toward native line
work, because the 3-bit greyscale panel reproduces line-on-white and
flat areas faithfully but collapses tonal mid-greys.

At final audit after this change archives, at least **60% of the
non-photograph image pool** SHALL have `form` in one of:

- `drawing` (pen, ink, charcoal, brush — excluding soft-graphite /
  conté tonal drawings)
- `woodblock` or `wood-engraving` (monochrome only)
- `ink-wash` (sumi-e, Zen brushwork)
- `poster` (flat-shape poster work — Sachplakat, Art Deco posters)

The remaining 40% MAY be tonal-print (etching, aquatint, crayon-
lithograph, tonal-drypoint); no hard ceiling, but individual creators
working primarily in tonal-print SHALL be capped at **no more than
3 items** in the gallery image pool. Excess tonal-print items remain
admissible on disk with `panel_verdict: flag` and are excluded from
triplet selection until they pass a panel-rendered review.

The audit SHALL list: total non-photograph images; count in each
`form`; share of pen-first forms as a percentage; per-creator counts
for tonal-print creators flagging any above the 3-item cap.

#### Scenario: Pen-first share at final audit

- **WHEN** the final audit reports 180 non-photograph images total,
  with 118 tagged `form: drawing`, `form: woodblock`, `form:
  wood-engraving`, `form: ink-wash`, or `form: poster`
- **THEN** the share is 65.5% — above the 60% floor — and the gate is
  satisfied

#### Scenario: Tonal-print creator above the cap

- **WHEN** Rembrandt holds 7 etching items in `corpus/images/`
- **THEN** the audit flags the creator as above the 3-item tonal-print
  cap and lists the 4 items that MUST be either re-classified as
  `panel_verdict: flag` or removed

### Requirement: Contemporary pen-and-ink canon coverage

The seed SHALL include a contemporary pen-and-ink / manga / ligne-
claire / caricature spine anchored by the 20 creators enumerated in
`openspec/changes/add-contemporary-pen-canon/lists/top-contemporary-
pen.yaml`, with coverage organised into four streams: manga (≥ 7),
Western comic-strip / cartoon (≥ 6), XKCD (≥ 12 strips), and
caricature + contemporary ink (≥ 6).

At archive, each `canon_weight: core` creator SHALL have ≥ 5 items,
each `canonical` SHALL have ≥ 3, allowing for one below-floor
creator per stream if web fetch demonstrably cannot retrieve more
at quality.

#### Scenario: Contemporary canon floor

- **WHEN** the final audit reports Tezuka 6, Toriyama 4, Miyazaki 4,
  Taniguchi 3, Matsumoto 3, Urasawa 4, Fujio 3 — and every other
  stream also at floor
- **THEN** the contemporary-canon gate is satisfied
