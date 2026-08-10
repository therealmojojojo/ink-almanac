/**
 * Byte values written into the PNG, one per panel level.
 *
 * These are SELECTORS, not tones. The device picks a level with
 * `RGB3BIT(v,v,v)` = `floor(v/32)`, so each entry must sit inside its own
 * 32-wide bucket — that is the only constraint on them.
 */
export const INKPLATE_PALETTE = [0, 36, 73, 109, 146, 182, 219, 255] as const;
export type PaletteValue = (typeof INKPLATE_PALETTE)[number];

/**
 * Measured appearance of each level from the 2026-08-10 step-wedge photographs.
 *
 * NOT USED FOR QUANTIZATION — retained as a record. Driving `nearestLevel` off
 * these values was tried and reverted the same day: it visibly destroyed detail
 * in the Gallery face, taking it back to roughly where the device-side dither
 * had it.
 *
 * The reason is the gaps. These values put 62 between levels 5 and 6 and 51
 * between 6 and 7, where the nominal palette has a uniform 36. Error diffusion
 * across a 62-wide gap is far coarser than across 36, so in the light midtones
 * where an etching like the Goya lives, fine tonal steps collapsed into visible
 * dither noise.
 *
 * The relative finding (levels 3 and 4 nearly coincide) reproduced across three
 * photographs and is probably real. The absolute curve is not trustworthy: a
 * phone camera applies its own tone curve, and normalising only the endpoints
 * does not remove it, so the interior values carry the camera's contrast as
 * well as the panel's. Redoing this properly needs a reference of known
 * reflectance in the frame — a calibrated grey card or printed step chart —
 * not a bare panel.
 *
 * See `firmware/docs/dither-hardware-validation.md`.
 */
export const PANEL_APPEARANCE_MEASURED = [0, 29, 65, 97, 110, 142, 204, 255] as const;

const PALETTE_SET = new Set<number>(INKPLATE_PALETTE);

export function isPaletteValue(v: number): v is PaletteValue {
  return PALETTE_SET.has(v);
}

export function nearestPaletteValue(v: number): number {
  let best: number = INKPLATE_PALETTE[0];
  let bestDist = Math.abs(v - best);
  for (let i = 1; i < INKPLATE_PALETTE.length; i++) {
    const p = INKPLATE_PALETTE[i]!;
    const d = Math.abs(v - p);
    if (d < bestDist) {
      bestDist = d;
      best = p;
    }
  }
  return best;
}

export function assertPaletteOnly(pixels: Uint8Array): void {
  for (let i = 0; i < pixels.length; i++) {
    if (!PALETTE_SET.has(pixels[i]!)) {
      throw new Error(`pixel ${i} has out-of-palette value ${pixels[i]}`);
    }
  }
}
