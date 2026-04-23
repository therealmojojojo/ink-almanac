# corpus-seed — delta for add-bw-graphic-arts-canon

## ADDED Requirements

### Requirement: Native-B&W graphic art share

The non-photograph image corpus SHALL be restricted to **native black-and-white
graphic art** — works authored in a monochrome medium whose tonal vocabulary
maps directly onto the 3-bit greyscale panel without conversion loss.

Admissible native-B&W forms: `etching`, `engraving`, `woodblock` (monochrome
only; ukiyo-e polychrome woodblocks are excluded here and remain categorised
separately), `wood-engraving`, `lithograph` (monochrome only), `drawing`
(graphite / ink / charcoal / conté / chalk), `ink-wash`, `silverpoint`, and
`aquatint`. `poster` items qualify only when the source is a monochrome
lithographic poster.

Inadmissible: any item with `form: painting` whose source was polychrome and
has been desaturated to greyscale. The 2026-04-19 review found such items
produce unacceptable quality on the 3-bit panel — tonal range collapses,
chroma-dependent structure disappears, and the image reads as muddy rather
than graphic. These items SHALL be refused at ingestion and removed when
encountered during audit.

The `corpus audit` report SHALL surface a "native-B&W graphic art" section
counting non-photograph images by form and flagging any `form: painting`
items that are not specifically catalogued under the aligned-nocturne
exception (see `Nocturne pool` — which may include paintings authored as
true tonal-monochrome works, e.g., grisaille, but SHALL NOT include
desaturated polychrome paintings).

#### Scenario: Desaturated painting refused at ingestion

- **WHEN** a staged sidecar declares `form: painting` with a source image
  that is a greyscale conversion of a polychrome oil painting
- **THEN** commit refuses the item with `form 'painting' is not a native-B&W
  graphic-art form; desaturated polychrome paintings are not admissible for
  the gallery image pool`

#### Scenario: Monochrome lithograph accepted

- **WHEN** a staged sidecar declares `form: lithograph` with a monochrome
  source (black on cream paper, e.g., a Daumier *Charivari* plate scanned
  from the original sheet)
- **THEN** commit accepts the item subject to the other ingestion gates

#### Scenario: Grisaille painting under nocturne exception

- **WHEN** a nocturne-pool sidecar declares `form: painting` for a work
  authored as a true tonal monochrome (e.g., grisaille, or a B&W-only
  medium)
- **THEN** the item is admissible only in the nocturne pool and the audit
  flags it as a named exception with its monochrome-authorship citation

### Requirement: Graphic-arts canon coverage

The seed SHALL maintain a non-photograph image spine anchored by canonical
graphic-arts creators enumerated in
`openspec/changes/add-bw-graphic-arts-canon/lists/top-bw-graphic-arts.yaml`
(28 creators spanning old-master printmaking, 19th-century print, fin-de-
siècle, German Expressionism, American 20th-century graphic work, modernist
drawing, Japanese ink tradition, contemporary drawing, and pen-and-ink
illustration).

At final audit after this change archives, the non-photograph image pool
SHALL include at least 5 canonical works from each `canon_weight: core`
creator and at least 3 from each `canonical` creator. The audit SHALL list
any creator below floor with the count short.

#### Scenario: Core-creator floor

- **WHEN** the final audit reports 4 canonical Dürer items committed
- **THEN** the graphic-arts coverage gate is not satisfied until Dürer
  reaches 5 canonical items
