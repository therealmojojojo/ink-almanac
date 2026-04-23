## Why

When a triplet's `summary` slot holds a text item, that text is rendered into the Summary face's `delight_text` zone — a small two-to-four-line band sized for a short fragment, not a full excerpt. The zone has a hard budget declared in `renderer/src/zones.ts`: **max 4 lines, max 24 chars per line**. Texts exceeding that budget cause the renderer to return HTTP `VERSE_OVERFLOW` instead of a PNG, and the face fails to render.

An audit of the current triplet pool (after the orientation pass) finds **114 of 134 triplets with text summaries — 85% — overflow the budget**. Examples: a 34-line Keats Ode excerpt, a 79-line Eliot section, a 89-line Topîrceanu ballad, all assigned to the summary slot. The pair-stands-alone invariant cannot be satisfied by a face that doesn't render.

Root cause: the authoring convention treated the summary slot as "a short text companion" without a machine-checkable size bound. The renderer enforces the bound at the HTTP boundary, but by then the triplet has already shipped. The validator is the right enforcement point.

## What Changes

- Adds one requirement to `corpus-triplets`: text fit for the summary slot.
  - When `summary` resolves to a text item, the text SHALL fit `delight_text`'s zone budget (4 lines / 24 chars per line per `renderer/src/zones.ts`).
  - Exceeding either dimension is a validation error.
- `pairing/corpus_validate.py` enforces the rule against the item's `text` or first `text_variants` entry.
- The zone budget constants are duplicated into `pairing/corpus_validate.py` with a comment tying them to `renderer/src/zones.ts`; they must be kept in sync when the zone is retuned.

## Capabilities

### Modified Capabilities

- `corpus-triplets`: adds the "Summary text fits delight_text zone" requirement.

## Impact

- **Spec**: one new requirement in `openspec/specs/corpus-triplets/spec.md` after archive.
- **Validator**: new check on `summary` when the slot is a text. Current pool: 117 validation errors under the new rule (a superset of the 114 auto-rejections triggered while drafting this change, because the validator checks all triplets including already-rejected ones).
- **Existing pool rebuild**: 114 triplets have been auto-rejected with `reject-layout` verdict and reason `"auto: summary text overflows delight_text budget (N lines, max M chars; budget 4/24)"`. Rebuilding them — substituting a shorter summary text or flipping to an image summary — is out of scope here; this change only ratifies the rule.
- **Renderer**: no change. The zone definition in `renderer/src/zones.ts` is already the source of truth; the validator mirrors it defensively.
- **Authoring flow**: no new tool. The validator run is the authoring checkpoint (same as every other triplet constraint).

## Relationship to other changes

This change is a sibling of `require-slot-orientation`. Both address the same underlying principle — slot assignments must honor the rendering zone's constraints — but they enforce different dimensions (orientation vs text size). Kept as separate changes because the affected pools, failure modes, and rebuild strategies are different. Could be folded into a single "slot fits zone" change later if more of these rules accumulate.
