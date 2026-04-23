export const INKPLATE_PALETTE = [0, 36, 73, 109, 146, 182, 219, 255] as const;
export type PaletteValue = (typeof INKPLATE_PALETTE)[number];

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
