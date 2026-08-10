## Context

The panel's images render soft and washed out while text stays crisp. The
cause is the Inkplate library's monochrome Floyd–Steinberg
(`ImageDither.cpp:39`), which diffuses quantization error against
`oldPixel & 0xE0` ∈ {0…224} while the panel emits the stretched palette
{0…255} — a 1.1384 gain mismatch that never enters the error term, plus
truncating quantization, per-term `>>4` shifts that discard small errors,
and an unsigned error accumulator. Measured against a real face: RMSE
19.97 and +19.05/255 brightness bias, versus 2.67 and −0.02 for a correct
implementation. Full derivation and measurements are in `proposal.md`.

The correction is to dither on the renderer, where the arithmetic is
already correct, and stop the device from dithering.

**The renderer-side infrastructure is already built and wired.** All five
modes export `ditherMask()`; `modes/index.ts:114-135` threads the result
into `renderToPng({ url, dither })`; `image/dither.ts` is a correct
palette-aware Floyd–Steinberg with mask support; `image/palette.ts`
provides `nearestPaletteValue()` and `assertPaletteOnly()`. The only
missing link is `render.ts:73`, which accepts the `dither` parameter and
discards it — its own comment says "Retained for API compatibility;
currently ignored."

This is the change that `rendering-pipeline` → "Selective dithering"
anticipated, but the reason recorded there (pngle decoder memory budget)
is not the reason it is happening.

## Goals / Non-Goals

**Goals:**

- Exactly one Floyd–Steinberg pass over the pixel data, performed by the
  implementation whose arithmetic is correct.
- Photo zones dithered; text and UI zones hard-quantized to nearest
  palette value, so glyph edges keep the crispness they have today.
- Lossless renderer→panel handoff: palette values map 1:1 onto panel
  levels 0–7 with no device-side arithmetic.
- A rollback that does not require reflashing the device.
- Hardware validation before the change becomes the default.

**Non-Goals:**

- Reinstating `prep.ts`'s full chain (linearize → contrast → endpoint
  crush → gamma re-encode). Only the palette-aware FS is wanted; the tonal
  manipulation was a contributor to the smudge that
  `improve-text-crispness` observed.
- Lanczos pre-resample of source images before Chromium. Separate change.
- Refetching sub-panel-resolution corpus images. Separate change.
- Changing the wake protocol, cadence, or any HA surface.

## Decisions

### D1: Dither in `render.ts`, not by reviving `prep.ts`

`render.ts` applies `floydSteinberg()` from `image/dither.ts` directly to
the greyscale screenshot, passing the mode's mask.

*Why:* `prep.ts` bundles FS with linearization, contrast ×1.1, and
endpoint crush at 0.10/0.90. Those tonal steps are what made the earlier
server-side experiment look wrong, and they are separable from the dither.
Calling `dither.ts` directly takes the correct part and leaves the rest.

*Alternative considered:* un-orphan `prep.ts` wholesale with the tonal
steps neutralized (`contrast: 1.0`, `blackCrush: 0`, `whiteCrush: 1`).
Rejected — it keeps a gamma round-trip that is lossy at 8-bit for no
benefit, and leaves live code whose defaults invite reintroduction of the
old behavior. `prep.ts` should be deleted rather than left orphaned a
second time.

### D2: Dither in sRGB code space, matching `INKPLATE_PALETTE`

Error diffusion operates on 8-bit values as they come out of Chromium,
quantizing to `INKPLATE_PALETTE` via `nearestPaletteValue()`.

*Why:* the palette is evenly spaced in code value, and the panel's level
selector is a straight `floor(v/32)`. Dithering in the same space the
palette is defined in keeps the mapping exact, and this is precisely the
configuration that measured RMSE 2.67 / bias −0.02 against the source.

*Alternative considered:* diffuse error in linear light, which is more
principled in general. Rejected for now — it would shift midtone
appearance in a way that needs its own hardware evaluation, and the
current measurement shows no bias worth chasing. Recorded as an open
question rather than folded in silently.

### D3: Masked dithering, not whole-face

Photo zones get error diffusion; everything else is hard-quantized to
nearest palette value via the `mask` parameter `dither.ts` already
supports.

*Why:* text is currently crisp and must stay so. Ink (`#000` → 0) and
paper (`#ececec` → 236) already sit at or adjacent to exact palette
entries; hard-quantizing them yields flat black on flat white with no
error-diffusion speckle in the paper. Diffusing error across a text field
would introduce exactly the palette-noise halo that
`improve-text-crispness` was fighting.

*Note:* hard-quantizing paper `236` → nearest palette `219`, not `255`.
This is a **visible change** — the paper background stops being pushed to
pure white by the library's truncation and becomes a light grey. See R3.

### D4: Runtime switch, so rollback needs no reflash

A `RENDERER_DITHER` env var selects `device` (current behavior, dither
parameter ignored) or `server` (new behavior). Default ships as `device`.

*Why:* the renderer and the firmware must agree, and each mismatch
direction degrades the panel — old firmware + new renderer double-dithers;
new firmware + old renderer hard-truncates to 3 bits and bands badly. An
env var makes the switch atomic on a renderer restart and makes rollback a
one-line change, rather than an OTA cycle, if the panel disagrees with the
simulation.

*Alternative considered:* content negotiation on a query parameter
(`/display/gallery.png?dither=none`), letting both firmware versions
coexist. Rejected as over-built for a single-device deployment; it also
puts a rendering decision in the firmware's URL construction, where it
would have to be kept in sync anyway.

### D5: Ordering — firmware first, then flip the renderer

OTA the firmware with `dither=false` while the renderer still emits
full-range greyscale, then flip `RENDERER_DITHER=server` and restart.

*Why:* it bounds the mismatch window to the time between OTA and restart,
during which the panel shows 3-bit banding — degraded but legible and
obviously wrong, which is a good failure mode. The reverse order shows
double-dither smudge, which is subtler and easier to mistake for the new
normal.

### D6: Verify mask rectangles before trusting them

The mask rectangles are hardcoded pixel coordinates written when the masks
were dead code (`summary.ts:337-340` at `x 48–650, y 500–770`;
`night.ts:137` at `x 576–1200`; `gallery.ts:222` computed from
`pixel_width/pixel_height`). Layouts have changed since — the gallery
caption band is 108 px while its own comment still says 72.

*Why it matters:* a mask that is too small leaves photo edges
hard-quantized (visible banding at the boundary); too large speckles
adjacent text. These are checked against rendered geometry, not assumed
correct because they compile.

## Risks / Trade-offs

**R1: The evidence is a simulation, not a photograph of the panel.**
The port is faithful to `ImageDither.cpp` and the palette assumption comes
from the repo's own `INKPLATE_PALETTE`, but reflectance spacing on real
e-paper is not guaranteed to be even. → Hardware validation gates the
default (`tasks.md`); the env var keeps the old path one restart away.

**R2: Mismatch between firmware and renderer degrades the panel.**
→ D4 + D5 bound the window and make the transient failure the obvious
one. Both components are operator-controlled on one LAN, single device.

**R3: Paper background changes from pure white to palette grey 219.**
Today the library's truncation pushes `#ececec` (236) up to level 7 (255),
so the panel paper is pure white. Correct nearest-palette quantization
sends 236 → 219 (level 6). Faces will read slightly greyer, and ink/paper
contrast drops from 255:0 to 219:0. → This is the honest rendering of the
chosen token, but if the panel looks flat, the fix is to change `--paper`
to `#ffffff` in `tokens.css` so it lands on level 7 deliberately rather
than through a quantization bug. Decide with the panel in hand, not now.

**R4: Reintroducing server-side quantization is the exact thing
`improve-text-crispness` reverted.** → That revert tested server
quantization *with the device still dithering*; the double pass was the
problem, not the server pass. This change moves both halves. The masked
approach additionally keeps text out of the diffusion path, which the
earlier whole-face `prepare()` did not.

**R5: Renders are ~50–80 ms slower** (one full-face FS pass in JS). →
Negligible against a multi-second e-ink refresh, and renders are already
gated on device poll cadence.

**R6: Existing renderer tests assert full 0–255 range output.** →
They encode the old contract and must invert to palette assertions;
`assertPaletteOnly()` already exists for this.

## Migration Plan

1. Land renderer changes with `RENDERER_DITHER` defaulting to `device`.
   The dither path is reachable but not active. One change does take effect
   on plain restart: output becomes genuinely single-channel
   (`toColourspace('b-w')`), which is not gated by the env var. Pixel values
   are unchanged — pngle decodes colour-type 0 by expanding `v[1] = v[2] =
   v[0]` (`pngle.c:350`), so the panel sees exactly what it saw before — but
   the Gallery payload drops 702 KB → 537 KB. Verified in both placements.
2. Validate on hardware: render one Gallery face each way, photograph the
   panel under identical light, compare.
3. If confirmed: OTA firmware with `dither=false`.
4. Flip `RENDERER_DITHER=server`, restart the renderer.
5. Observe one full rotation (Summary → Weather → Gallery → Night →
   Now-Playing) before removing the escape hatch.
6. Once settled, delete `prep.ts`, drop the env var, and make server-side
   dithering unconditional.

**Rollback:** set `RENDERER_DITHER=device` and restart. The firmware's
`dither=false` then receives full-range greyscale and hard-truncates —
banded but legible — until the firmware is reverted. If the panel must be
correct immediately, revert the firmware too.

## Open Questions

- **Does linear-light error diffusion look better on the panel than
  sRGB-space?** D2 defers this. Worth a single-face comparison during
  step 2, since the harness will already be set up.
- **Should `--paper` move to `#ffffff`?** Depends on how palette grey 219
  reads on hardware (R3). Cannot be settled from a simulation.
- **Do the 1-bit partial-update paths need anything?** Night phrase
  bitmaps and clock digits go through `drawBitmap1Bit`/`fillRect1Bit`, not
  the PNG decode path, so they should be untouched — but the Night face's
  cold-state over-paint interacts with what the 3-bit PNG left behind, and
  that PNG's pixel values are changing. Verify during step 5.
