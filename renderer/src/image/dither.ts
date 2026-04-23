import { INKPLATE_PALETTE, nearestPaletteValue } from './palette.js';

export interface DitherMask {
  width: number;
  height: number;
  /** true where the pixel should be dithered, false where it should be hard-quantized */
  data: Uint8Array;
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
