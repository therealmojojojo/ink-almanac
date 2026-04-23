## Why

Review on 2026-04-19 showed that the tonal printmaking anchors of
`add-bw-graphic-arts-canon` (Goya aquatints, Rembrandt etchings,
Piranesi/Meryon etchings, Daumier/Redon lithographs, Whistler etchings)
render poorly on the 3-bit panel — not because the scans are bad, but
because aquatint/crayon-lithograph/dense cross-hatching rely on a tonal
range the device cannot reproduce. Twenty-one items were dropped; several
creators are now below their coverage floor.

This change opens a **contemporary pen-and-ink / screentone / ligne-claire
canon** to rebuild image-pool depth with material that is native-friendly
to the panel: pure line on white paper, solid flats, calligraphic brush,
screentone dots. Unlike the old-master printmaking canon, this is the
medium the e-ink panel was made for.

The operator specifically requested manga (kid-anchoring), XKCD (famous
strips), and caricature.

## What Changes

- Add a **contemporary-pen** lineage group of 20 creators across four
  streams: manga, Western comic-strip / cartoon, XKCD, caricature +
  contemporary ink draughtsmen. All items route `rights_tier:
  personal_library` (20th/21st-c work under copyright).
- XKCD is fetched via Randall Munroe's public JSON API at
  `xkcd.com/<n>/info.0.json` — no key, CC-BY-NC 2.5. The API directly
  serves the high-resolution PNG. This is the simplest fetch path in the
  project and will act as the proof-of-concept first batch.
- Comic-strip and manga work is fetched from Commons where available,
  from publisher / foundation archives (Tezuka Productions, Hergé
  Foundation, Hirschfeld Foundation) where not.
- **De-emphasise the etching-heavy old-master anchors** in the existing
  `add-bw-graphic-arts-canon`: cap each old-master etcher at 2–3 items
  (the highest-contrast plates only). Reallocate the canon coverage floor
  to the new pen streams.
- The `corpus-seed` spec gains a new requirement codifying
  "pen-and-ink over tonal-print" as the preferred non-photograph medium
  for the 3-bit panel.

## Impact

- Affected specs: `corpus-seed` (new "Pen-first non-photograph spine"
  requirement; adjust "Graphic-arts canon coverage" targets).
- Affected code: extend `pairing/corpus_api_fetch.py` with an `xkcd`
  source adapter; no other changes required. Commons-primary path
  already serves the manga and comic-strip fetches.
- Affected corpus: +30–60 items expected across Stream 1 (XKCD, ~15
  strips), Stream 2 (comic-strip, ~30–40), Stream 3 (manga, ~40–50
  panels), Stream 4 (caricature, ~20).
- Interaction with `add-bw-graphic-arts-canon`: this change is
  complementary, not replacing. Graphic-arts retains Beardsley, Hakuin,
  Sesshū, Vallotton, Munch-woodcuts, Kirchner-woodcuts, Kollwitz-
  woodcuts — the pen-and-ink/woodcut subset that does render well.
