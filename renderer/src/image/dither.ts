import { INKPLATE_PALETTE, nearestPaletteValue } from './palette.js';
import { BLUE_NOISE_RANK, BLUE_NOISE_SIZE } from './blueNoise.generated.js';

export interface DitherMask {
  width: number;
  height: number;
  /** true where the pixel should be dithered, false where it should be hard-quantized */
  data: Uint8Array;
}

/** Panel geometry — every mask is built at full face size. */
export const FACE_W = 1200;
export const FACE_H = 825;

/**
 * A mask covering a single rectangle of the face, clamped to its bounds.
 *
 * Every mode's photo zone is one rectangle, so this replaces the hand-rolled
 * nested loop each of them used to carry. Coordinates are CSS px = panel px.
 * `check-dither-masks` verifies the result against the laid-out geometry.
 */
export function rectMask(x: number, y: number, w: number, h: number): DitherMask {
  const x0 = Math.max(0, Math.round(x));
  const y0 = Math.max(0, Math.round(y));
  const x1 = Math.min(FACE_W, Math.round(x + w));
  const y1 = Math.min(FACE_H, Math.round(y + h));
  const data = new Uint8Array(FACE_W * FACE_H);
  for (let py = y0; py < y1; py++) {
    data.fill(1, py * FACE_W + x0, py * FACE_W + x1);
  }
  return { width: FACE_W, height: FACE_H, data };
}

/**
 * Blue-noise ordered dithering — the photo path.
 *
 * Each masked pixel falls between two palette entries; a threshold from the
 * baked blue-noise tile decides which one it takes. Unmasked pixels
 * hard-quantize, exactly as under `floydSteinberg`, so text keeps clean edges.
 *
 * Chosen over Floyd-Steinberg after measuring both against ideal continuous
 * tone at a range of perceptual blur radii. FS is more accurate under close
 * inspection, because it conserves error exactly; but its error is correlated
 * and shows as worm and maze texture. Blue noise places the same error at high
 * spatial frequency, which disappears with distance — it wins on all four test
 * images at a 4px blur (by up to 3.6x) and was preferred on the panel by the
 * operator, 2026-08-10.
 *
 * The panel is read from across a room, so the far-field result is the one that
 * matters. Scoring only at 1px is what made the first analysis prefer FS.
 */
export function blueNoiseDither(
  input: Uint8Array,
  width: number,
  height: number,
  mask?: DitherMask,
): Uint8Array {
  if (input.length !== width * height) {
    throw new Error(`dither: input size ${input.length} != ${width}×${height}`);
  }
  if (mask && (mask.width !== width || mask.height !== height)) {
    throw new Error('dither: mask size mismatch');
  }
  const out = new Uint8Array(input.length);
  const tile = BLUE_NOISE_SIZE;
  const scale = tile * tile;

  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const idx = y * width + x;
      const v = input[idx]!;
      if (mask && mask.data[idx] === 0) {
        out[idx] = nearestPaletteValue(v);
        continue;
      }
      // Bracketing palette entries. INKPLATE_PALETTE is ascending, so this
      // finds the pair the value sits between.
      let lo = 0;
      while (lo < INKPLATE_PALETTE.length - 2 && INKPLATE_PALETTE[lo + 1]! <= v) lo++;
      const a = INKPLATE_PALETTE[lo]!;
      const b = INKPLATE_PALETTE[lo + 1]!;
      const span = b - a;
      const frac = span === 0 ? 0 : Math.min(1, Math.max(0, (v - a) / span));
      const threshold =
        (BLUE_NOISE_RANK[(y % tile) * tile + (x % tile)]! + 0.5) / scale;
      out[idx] = threshold < frac ? b : a;
    }
  }
  return out;
}

/**
 * Nearest-palette quantization with no error diffusion, for faces that have no
 * photographic zone at all (Weather). Equivalent to `floydSteinberg` with an
 * all-zero mask, without allocating the mask.
 */
export function quantizeToPalette(input: Uint8Array): Uint8Array {
  const out = new Uint8Array(input.length);
  for (let i = 0; i < input.length; i++) out[i] = nearestPaletteValue(input[i]!);
  return out;
}

/**
 * Palette-aware Floyd-Steinberg for 8-bit greyscale input.
 * Input is a linear greyscale Uint8 buffer (one byte per pixel, row-major).
 * If `mask` is provided, only masked pixels get error-diffusion; others hard-quantize.
 * Output is a fresh Uint8Array where every byte ∈ INKPLATE_PALETTE.
 */
export function floydSteinberg(
  input: Uint8Array,
  width: number,
  height: number,
  mask?: DitherMask,
): Uint8Array {
  if (input.length !== width * height) {
    throw new Error(`dither: input size ${input.length} != ${width}×${height}`);
  }
  // Work in a float buffer for error diffusion.
  const buf = new Float32Array(input.length);
  for (let i = 0; i < input.length; i++) buf[i] = input[i]!;

  const out = new Uint8Array(input.length);

  const isDitherPixel = (x: number, y: number): boolean => {
    if (!mask) return true;
    if (mask.width !== width || mask.height !== height) {
      throw new Error('dither: mask size mismatch');
    }
    return mask.data[y * width + x] !== 0;
  };

  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const idx = y * width + x;
      const old = buf[idx]!;
      const quant = nearestPaletteValue(old);
      out[idx] = quant;

      if (!isDitherPixel(x, y)) continue;

      const err = old - quant;
      // Floyd-Steinberg distribution
      if (x + 1 < width) buf[idx + 1] = buf[idx + 1]! + (err * 7) / 16;
      if (y + 1 < height) {
        if (x > 0) buf[idx + width - 1] = buf[idx + width - 1]! + (err * 3) / 16;
        buf[idx + width] = buf[idx + width]! + (err * 5) / 16;
        if (x + 1 < width) buf[idx + width + 1] = buf[idx + width + 1]! + (err * 1) / 16;
      }
    }
  }

  return out;
}

export { INKPLATE_PALETTE };
