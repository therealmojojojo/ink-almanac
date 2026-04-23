## ADDED Requirements

### Requirement: Image slot orientation

Each image slot in a triplet has a rendering zone with a fixed aspect ratio on the 1200×825 panel, and images are fitted into those zones with `object-fit: cover`. The following orientation constraints SHALL be enforced at validation time based on an image item's `pixel_width` (W) and `pixel_height` (H):

- **`summary`** — when the summary slot holds an image, it SHALL be landscape or square (`W ≥ H`). Portrait images (`H > W`) are rejected.
- **`gallery`** — when the gallery slot holds an image (visual-day flavor), any orientation is permitted (landscape, portrait, or square).
- **`aligned_nocturne`** — the night image SHALL be portrait or square (`H ≥ W`). Landscape images (`W > H`) are rejected.

Square images (`W == H`) are allowed in every image slot.

Text slots have no orientation and are unaffected.

This is a composition requirement, not a fidelity one: the Summary face's delight zone is a wide landscape band; a portrait image fitted into it crops out nearly the full composition. The Night face's nocturne column is a narrow tall band; a landscape image fitted into it collapses to a thin horizontal strip of the middle. The Gallery face's canvas is large and near-square enough to accept any orientation without catastrophic loss.

Enforcement is at authoring time (in `corpus validate`), not at render time — the renderer applies the zone and trusts the authoring layer.

#### Scenario: Portrait image in summary slot

- **WHEN** a triplet declares `summary: utamaro-beauty-yamauba-kintaro` where that image has `pixel_width: 2250, pixel_height: 3000`
- **THEN** validation rejects the triplet with `summary slot -> 'utamaro-beauty-yamauba-kintaro' is portrait (2250x3000); summary requires landscape/square`

#### Scenario: Landscape image in aligned_nocturne slot

- **WHEN** a triplet declares `aligned_nocturne: brassai-pont-neuf-dawn` where that image has `pixel_width: 3000, pixel_height: 2000`
- **THEN** validation rejects the triplet with `aligned_nocturne slot -> 'brassai-pont-neuf-dawn' is landscape (3000x2000); aligned_nocturne requires portrait/square`

#### Scenario: Portrait image in gallery slot

- **WHEN** a visual-day triplet declares `gallery: friedrich-wanderer-mist` where that image has `pixel_width: 2327, pixel_height: 2980`
- **THEN** validation accepts the triplet; gallery is unconstrained on orientation

#### Scenario: Square image in any image slot

- **WHEN** a triplet declares any image slot (`summary`, `gallery`, or `aligned_nocturne`) pointing to an item with `pixel_width == pixel_height`
- **THEN** validation accepts the triplet; square is allowed in every image slot
