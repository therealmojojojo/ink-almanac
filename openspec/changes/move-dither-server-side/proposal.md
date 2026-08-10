# Move dithering server-side

> **Status — 2026-08-10**: draft. Supersedes the default path established by
> `improve-text-crispness` (archived), and is the "future change" that
> `rendering-pipeline` → "Selective dithering" explicitly anticipated —
> though for a different reason than the one recorded there.

## Why

The operator reported that panel **text is crisp but images look soft and
washed out**. Investigation traced this to the Inkplate library's
monochrome Floyd–Steinberg implementation, which the firmware invokes by
passing `dither=true` (`firmware/src/hal/real/RealDisplay.h:31`).

`ditherGetPixelBmp` (`InkplateLibrary/src/include/ImageDither.cpp:39`)
quantizes and diffuses error like this:

```c
uint8_t newPixel   = oldPixel & 0b11100000;   // → {0, 32, 64, … 224}
uint8_t quantError = oldPixel - newPixel;
return newPixel >> 5;                          // → panel level 0–7
```

The error is settled against `newPixel`, but the panel renders that level
at the stretched palette `[0, 36, 73, 109, 146, 182, 219, 255]`:

| Level | Error diffused against | Panel emits | Un-accounted |
|---|---|---|---|
| 1 | 32 | 36 | +4 |
| 3 | 96 | 109 | +13 |
| 5 | 160 | 182 | +22 |
| 7 | 224 | 255 | +31 |

A gain mismatch of 255/224 = **1.1384** that never enters the error term.
Every pixel emits more light than the algorithm believes it did, and the
surplus is never diffused away.

A faithful port of the library function, run against a real
`/display/gallery.png` (Goya, *Disasters of War #1*, 2026-08-10 rotation):

| | RMSE vs source | Brightness bias | Local contrast |
|---|---|---|---|
| Device (Inkplate library) | **19.97** | **+19.05** | 10.64 |
| Correct Floyd–Steinberg | 2.67 | −0.02 | 9.41 |

**7.5× worse**, with images rendering ~19/255 too bright.

Three secondary defects in the same function compound it:

1. **Truncation, not rounding** — `& 0xE0` always rounds down, so
   `quantError` is never negative.
2. **Per-term shift truncation** — each diffusion term is shifted
   independently (`(e*5)>>4`, `(e*7)>>4`, `(e*1)>>4`, `(e*3)>>4`). The
   1/16 term is **zero** for any error below 16 and the 3/16 term is zero
   below 6, so error leaks out of the system instead of being conserved.
3. **Unsigned accumulator** — `uint8_t ditherBuffer[2][E_INK_WIDTH + 20]`
   (`Image.h:153`) cannot hold negative error and wraps at 256.

### Why text is unaffected

The face tokens are `--ink: #000` and `--paper: #ececec`:

- ink `0` → `0 & 0xE0` = 0 → level 0 → emits **0**. Exact, zero error.
- paper `236` → `236 & 0xE0` = 224 → level 7 → emits **255**.

Both endpoints land exactly on panel levels, and the bug *widens* the
ink/paper gap rather than muddying it. Text therefore renders at maximum
contrast with no error to diffuse; only midtones — photographs — pass
through the broken arithmetic. This asymmetry is exactly what the operator
observed, and it was predicted by the simulation before being matched
against the report.

### Why the existing default exists, and why it is now wrong

`improve-text-crispness` removed the server-side `prepare()` chain after
observing "visible smudge on hardware (double-dither on already-quantized
input)". That diagnosis was correct for what was tested: the server was
quantizing **while the device was still dithering**. The conclusion drawn
— that the device's single pass is therefore the right one — does not
follow. The device's pass is arithmetically broken; the server's is not.
Both halves must move together.

## What Changes

- The renderer performs Floyd–Steinberg error diffusion onto the Inkplate
  palette server-side, using the existing (currently orphaned)
  `renderer/src/image/dither.ts` and `renderer/src/image/palette.ts`.
- Dithering is **masked to photo zones** via the already-implemented
  `ditherMask()` functions in `renderer/src/modes/gallery.ts:212` and
  `renderer/src/modes/night.ts`. Text and UI zones are hard-quantized to
  nearest palette value, keeping glyph edges free of palette-noise halo.
- `/display/{mode}.png` output becomes palette-constrained: every pixel
  value ∈ `[0, 36, 73, 109, 146, 182, 219, 255]`.
- **BREAKING (device contract)**: firmware draws with `dither=false`
  (`RealDisplay.h:31`). The renderer and firmware SHALL be deployed
  together; a mismatch in either direction degrades the panel.
- Output PNG becomes true single-channel greyscale via
  `sharp.toColourspace('b-w')`. `sharp.greyscale()` alone desaturates but
  leaves three identical channels; the current response is RGB.
  Measured: 702 KB → 537 KB per wake.

The handoff is lossless by construction. With `dither=false` the device
applies `RGB3BIT(v,v,v) = (256·v)>>13 = floor(v/32)`, and the palette maps
1:1 onto panel levels:

```
0→0   36→1   73→2   109→3   146→4   182→5   219→6   255→7
```

`INKPLATE_PALETTE` was evidently chosen for exactly this.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `rendering-pipeline`: "Image-preparation chain" and "Selective
  dithering" invert — server-side Floyd–Steinberg becomes required rather
  than forbidden, scoped to photo zones. "Rendering engine" drops its
  no-palette-quantization clause. This also resolves a standing
  contradiction in the spec: "HTTP endpoint surface" and "Output
  specifications" already assert palette-constrained output, which the
  later requirements contradict. After this change the earlier statements
  become true again.
- `device-firmware`: adds an explicit requirement that the panel draw path
  passes `dither=false`, and that firmware and renderer versions are
  co-deployed.

## Impact

**Code**

- `renderer/src/render.ts` — apply mask-aware dither; emit `b-w` colourspace
- `renderer/src/image/prep.ts`, `dither.ts`, `palette.ts` — un-orphan; `prep.ts`'s
  contrast/crush chain is **not** reinstated, only palette-aware FS
- `renderer/src/modes/*.ts` — all five modes **already** export `ditherMask()`
  and `modes/index.ts` already threads it into `renderToPng()`; the masks
  become live rather than new. Their hardcoded rectangles (e.g.
  `summary.ts:337-340`, `night.ts:137`) predate later layout edits and need
  re-verification against current geometry
- `firmware/src/hal/real/RealDisplay.h:31` — `dither=false`
- Renderer tests asserting full 0–255 range must invert to palette assertions

**Systems**

- Device download size drops ~24% per wake; marginal battery gain
- Renderer CPU rises by one full-face FS pass per render (~50–80 ms);
  irrelevant against e-ink refresh time
- No change to HA, corpus, pairing, or the wake protocol

**Risk**

The evidence is a simulation of library source, not a photograph of the
panel. It assumes the eight levels are approximately evenly spaced in
reflectance — which is what `INKPLATE_PALETTE` already encodes. Hardware
validation on a single face gates the rollout (see `tasks.md`).

**Out of scope**

- Lanczos pre-resample of source images before Chromium (Chromium
  downsamples with a bilinear-class filter, costing ~26–33% of achievable
  high-frequency detail). Separate change; compounds with this one.
- Refetching the ~415 corpus images at or below panel resolution.
