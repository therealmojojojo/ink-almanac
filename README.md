# Inkplate

Kitchen-fridge dashboard on an Inkplate 10 (3-bit greyscale e-ink, 1200×825). A server-side pipeline pairs a curated corpus of images and texts into daily "triplets" — anchor + summary + gallery — and renders them for the device. Weather, Now-Playing, Night, and Gallery faces swap through the day.

## Where things live

- `openspec/` — **source of truth** for requirements, specs, and in-flight change proposals. Start at `openspec/specs/` for ratified capabilities and `openspec/changes/` for work-in-progress.
- `corpus/` — curated works (images + texts), controlled vocabulary, manifest. Schema in `openspec/specs/corpus-schema/`.
- `renderer/` — server-side HTML → PNG renderer for each face.
- `pairing/` — Python tooling for the corpus (validator today; full ingestion CLI pending, see `openspec/changes/add-corpus-ingestion/`).
- `firmware/` — Inkplate 10 device code.
- `ha/` — Home Assistant integration (weather, Now-Playing, scheduling).
- `requirements/Requirements.md` — **reference only**, superseded by `openspec/specs/`.

## First read

`CLAUDE.md` at the repo root explains architecture, runtime topology, and conventions.
