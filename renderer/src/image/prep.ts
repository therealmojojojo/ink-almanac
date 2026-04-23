// ORPHANED as of the `improve-text-crispness` change: no runtime code path
// calls `prepare()`. The default render pipeline now emits 8-bit greyscale
// PNGs directly from Chromium (see `renderer/src/render.ts`) and lets the
// device's Inkplate library perform the single Floyd-Steinberg dither onto
// the 8-shade panel palette. Running this chain in addition produced visible
// smudge on hardware (double-dither on already-quantized input).
//
// Retained because the follow-up photo-mode quantization change will reuse
// the Floyd-Steinberg + palette-mapping logic here, scoped to photo zones
// and combined with `dither=false` in firmware for those modes. See the
// `improve-text-crispness` design.md for the recorded hardware findings.

import sharp from 'sharp';
import { floydSteinberg, type DitherMask } from './dither.js';
import { assertPaletteOnly, nearestPaletteValue } from './palette.js';

export interface PrepOptions {
  blackCrush?: number; // 0..1 default 0.05
  whiteCrush?: number; // 0..1 default 0.95
  contrast?: number; // linear multiplier around 0.5, default 1.1
  dither: boolean | DitherMask;
}

/**
 * Full image-preparation chain: greyscale → linearize → contrast → saturation-zero
 * (implicit via greyscale) → crush → (palette-aware FS dither if enabled) → quantize
 * → write PNG. Returns a single-channel PNG buffer with values ∈ Inkplate palette.
 */
export async function prepare(
  rawPngOrRgb: Buffer,
  opts: PrepOptions,
): Promise<Buffer> {
  // Crush defaults loosened from 0.05/0.95 → 0.10/0.90 so anti-aliased glyph
  // edges (which sit in the 0.70–0.95 band) survive quantization instead of
  // getting hard-clipped to pure white. Essential with 2× supersample: the
  // downsampled greyscale ramp at edges gives the 8-shade palette real work.
  const blackCrush = opts.blackCrush ?? 0.10;
  const whiteCrush = opts.whiteCrush ?? 0.90;
  const contrast = opts.contrast ?? 1.1;

  // 1. greyscale + linearize (remove sRGB gamma) + saturation zero (implicit in greyscale)
  const { data: linearGrey, info } = await sharp(rawPngOrRgb)
    .greyscale()
    .gamma(1.0, 2.2) // remove sRGB gamma, emit linear
    .raw()
    .toBuffer({ resolveWithObject: true });

  const { width, height, channels } = info;
  if (channels !== 1) {
    throw new Error(`prep: expected 1-channel greyscale, got ${channels}`);
  }

  // 2. contrast around mid, then crush endpoints. Work in float [0,1].
  const n = width * height;
  const scratch = new Float32Array(n);
  for (let i = 0; i < n; i++) {
    const v = linearGrey[i]! / 255;
    let c = (v - 0.5) * contrast + 0.5;
    if (c < blackCrush) c = 0;
    else if (c > whiteCrush) c = 1;
    if (c < 0) c = 0;
    else if (c > 1) c = 1;
    scratch[i] = c;
  }

  // 3. re-apply sRGB gamma so downstream quantization matches human perception
  //    against Inkplate's perceptually-spaced palette.
  const reencoded = new Uint8Array(n);
  for (let i = 0; i < n; i++) {
    const linear = scratch[i]!;
    // sRGB encode
    const srgb =
      linear <= 0.0031308 ? 12.92 * linear : 1.055 * Math.pow(linear, 1 / 2.4) - 0.055;
    reencoded[i] = Math.max(0, Math.min(255, Math.round(srgb * 255)));
  }

  // 4. dither (if requested) OR hard quantize
  let quantized: Uint8Array;
  if (opts.dither === false) {
    quantized = new Uint8Array(n);
    for (let i = 0; i < n; i++) quantized[i] = nearestPaletteValue(reencoded[i]!);
  } else if (opts.dither === true) {
    quantized = floydSteinberg(reencoded, width, height);
  } else {
    quantized = floydSteinberg(reencoded, width, height, opts.dither);
  }

  // 5. palette self-check
  assertPaletteOnly(quantized);

  // 6. write PNG (8-bit greyscale, no alpha)
  const png = await sharp(quantized, {
    raw: { width, height, channels: 1 },
  })
    .png({ compressionLevel: 9, palette: false })
    .toBuffer();

  return png;
}
