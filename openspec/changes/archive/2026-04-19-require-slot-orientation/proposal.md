## Why

The three image-bearing slots in a triplet (`summary`, `gallery`, `aligned_nocturne`) render into zones with fixed aspect ratios on the 1200×825 panel. Each zone has a natural orientation, and forcing an image into the wrong orientation produces a catastrophic crop — loses composition, loses faces, centers on an arbitrary mid-band.

The worst case today is portrait images in the Summary face's delight zone: the zone is wide-and-short, the image is tall-and-narrow, and `object-fit: cover` crops out almost everything that makes the work recognizable. Example: `utamaro-beauty-yamauba-kintaro` (2250×3000) used as summary in `antimagice-stillness` renders as mostly a dark mass with a sliver of calligraphy. The pair-stands-alone invariant (`corpus-triplets` "Pair-stands-alone") cannot be satisfied by an unrecognizable image.

An audit across the current 301 triplets finds **94** with portrait summary slots — nearly a third of the pool. Symmetric checks for the other slots: the nocturne zone is tall-and-narrow (right column of the Night face), so landscape images suffer the same collapse there. The Gallery face has a large near-square canvas and handles all orientations acceptably.

Codifying these constraints as spec-level requirements — and enforcing them in `corpus validate` — prevents future authoring mistakes and gives the existing pool a clear rebuild target.

## What Changes

- Adds one requirement to `corpus-triplets`: orientation rules per slot.
  - `summary`: landscape or square only; portrait is rejected.
  - `gallery`: any orientation (landscape, portrait, square).
  - `aligned_nocturne`: portrait only; landscape is rejected. (Square is allowed as a boundary case — `pixel_width == pixel_height`.)
- Text slots are unaffected (no orientation).
- `corpus validate` enforces the rule; offending triplets error with a clear message.

## Capabilities

### Modified Capabilities

- `corpus-triplets`: adds the "Image slot orientation" requirement.

## Impact

- **Spec**: one new requirement in `openspec/specs/corpus-triplets/spec.md` after this change archives.
- **Validator**: `pairing/corpus_validate.py` gains the orientation check on the `summary` and `aligned_nocturne` slots. Gallery is unconstrained.
- **Existing pool**: 94 triplets currently violate the summary rule; they need either a landscape/square substitute for the summary slot or a flavor change (to a text summary). The nocturne rule may catch a smaller number — to be counted once implementation lands. Rebuild is out of scope for this change; this proposal only ratifies the constraint and turns it on in the validator.
- **No code outside `pairing/`** is affected. The renderer does not consult orientation — it applies `object-fit` and trusts the authoring layer.
