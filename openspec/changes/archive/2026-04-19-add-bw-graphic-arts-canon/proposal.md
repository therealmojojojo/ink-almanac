## Why

The 34 non-photograph image items currently labeled painting/lithograph/drawing
were assembled opportunistically and include nine oil paintings whose colour
content does not survive the 3-bit greyscale panel. Review (2026-04-19) with the
operator found their rendered quality unacceptable. This change resets the
non-photographic image corpus around **native black-and-white graphic art** —
etchings, engravings, wood engravings, lithographs, drawings, and ink works
that were authored in the tonal vocabulary the device reproduces.

The 441 black-and-white photographs committed under `top-50-bw-photographers`
(2026-04-18/19) remain in place and are unaffected by this change.

## What Changes

- Remove the nine `form: painting` sidecars + binaries from the corpus (six
  nocturne, two image, one personal_library/nocturne). No triplets reference
  these items; zero triplet pool impact.
- Adopt a canonical list of **28 black-and-white graphic artists** as the new
  non-photograph spine, structured to mirror the photographer pipeline:
  stage-1 shortlist of creators, stage-2 works list per creator, museum-API-
  first fetch (avoiding the DuckDuckGo-first quality problems observed in
  the photographer harvest).
- Introduce a new seed-corpus requirement: **non-photograph images must be
  native-B&W** in their source medium. Paintings converted via desaturation
  are refused at ingestion.

## Impact

- Affected specs: `corpus-seed` (new "Native-B&W graphic art share" requirement
  alongside the existing "Black-and-white photography share" requirement;
  minor clarification that painting-to-B&W conversion is not "native-B&W").
- Affected code: none yet; the ingestion CLI already refuses
  `panel_fidelity: color-dependent` and already supports personal_library
  routing, which is the tier most of these creators will land in.
- Affected corpus: -9 items (paintings removed); +200–250 items expected
  across the 28 creators once stage-2 works lists are fetched at 5–10 works
  each.
- Affected triplets: none currently; new triplets can form once items land.

## Sources

The fetch plan for this change deliberately avoids the DuckDuckGo-first
harvest that produced ~87% pending stage-2 matches in the photographer
pipeline. Per-creator source priority is museum-API-first:

- Rijksmuseum, Met Open Access, National Gallery of Art Washington, Museo
  del Prado, Art Institute of Chicago, British Museum, Library of Congress
  PPOC, BnF Gallica, William Blake Archive, Albertina Vienna, Munch Museum
  Oslo, Käthe-Kollwitz-Museum, and Tokyo National Museum as primary
  archives.
- Wikimedia Commons Featured Pictures as a cross-archive "best available
  scan" aggregator.
- `personal_library` web-fetch only for 20th/21st-century creators whose
  works are not available via PD museum APIs (Kentridge, Celmins,
  Steinberg, Kirchner, Otto Dix, Lynd Ward).

Per-creator source routing is recorded in
`lists/top-bw-graphic-arts.yaml`.
