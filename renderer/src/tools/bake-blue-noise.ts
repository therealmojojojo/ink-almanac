/**
 * Generate the blue-noise threshold matrix used by the photo dither.
 *
 * Void-and-cluster (Ulichney, "The void-and-cluster method for dither array
 * generation", 1993). The result is a 64x64 tile of thresholds whose energy
 * sits at HIGH spatial frequency, so the dot pattern it produces is invisible
 * at viewing distance where a low-frequency pattern would not be.
 *
 * Why not Floyd-Steinberg for photos: FS diffuses error into neighbours, which
 * correlates the output and produces worm and maze textures. Measured against
 * ideal continuous tone on four gallery images, FS is more accurate under close
 * inspection but blue noise wins at every realistic viewing distance — 4 of 4
 * images at a 4px perceptual blur, by up to 3.6x. Confirmed on the panel by the
 * operator, 2026-08-10. See `firmware/docs/dither-hardware-validation.md`.
 *
 * Run: npm run bake:blue-noise
 * Writes `src/image/blueNoise.generated.ts`. Deterministic — the same seed
 * always yields the same matrix, so the output is reproducible and diffable.
 */
import fs from 'node:fs/promises';
import path from 'node:path';
import { ROOT } from '../config.js';

const SIZE = 64;
const SIGMA = 1.5;
const N = SIZE * SIZE;
const SEED = 7;

/** Deterministic PRNG so a rebuild reproduces the committed matrix exactly. */
function mulberry32(a: number): () => number {
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/**
 * Gaussian weights over a cyclic neighbourhood, truncated at 3 sigma.
 * Cyclic so the tile repeats seamlessly across the face.
 */
const RADIUS = Math.ceil(SIGMA * 3);
const KERNEL: number[] = [];
for (let dy = -RADIUS; dy <= RADIUS; dy++) {
  for (let dx = -RADIUS; dx <= RADIUS; dx++) {
    KERNEL.push(Math.exp(-(dx * dx + dy * dy) / (2 * SIGMA * SIGMA)));
  }
}

/**
 * Filtered field, maintained incrementally.
 *
 * Recomputing the full convolution after every single-pixel toggle would be
 * O(N * k^2) per step and far too slow; toggling one pixel only shifts the
 * field by that pixel's kernel, which is O(k^2).
 */
class Field {
  readonly value = new Float64Array(N);

  toggle(idx: number, sign: number): void {
    const px = idx % SIZE;
    const py = (idx / SIZE) | 0;
    let k = 0;
    for (let dy = -RADIUS; dy <= RADIUS; dy++) {
      const y = (py + dy + SIZE) % SIZE;
      for (let dx = -RADIUS; dx <= RADIUS; dx++) {
        const x = (px + dx + SIZE) % SIZE;
        this.value[y * SIZE + x] += sign * KERNEL[k]!;
        k++;
      }
    }
  }
}

function tightestCluster(binary: Uint8Array, field: Field): number {
  let best = -Infinity;
  let at = -1;
  for (let i = 0; i < N; i++) {
    if (binary[i] === 1 && field.value[i]! > best) {
      best = field.value[i]!;
      at = i;
    }
  }
  return at;
}

function largestVoid(binary: Uint8Array, field: Field): number {
  let best = Infinity;
  let at = -1;
  for (let i = 0; i < N; i++) {
    if (binary[i] === 0 && field.value[i]! < best) {
      best = field.value[i]!;
      at = i;
    }
  }
  return at;
}

function build(): Int32Array {
  const rnd = mulberry32(SEED);
  const binary = new Uint8Array(N);
  const field = new Field();

  const initial = Math.floor(N / 10);
  let placed = 0;
  while (placed < initial) {
    const i = Math.floor(rnd() * N);
    if (binary[i] === 0) {
      binary[i] = 1;
      field.toggle(i, +1);
      placed++;
    }
  }

  // Phase 0 — spread the prototype until removing the tightest cluster and
  // filling the largest void pick the same pixel (a fixed point).
  for (let guard = 0; guard < 10000; guard++) {
    const c = tightestCluster(binary, field);
    binary[c] = 0;
    field.toggle(c, -1);
    const v = largestVoid(binary, field);
    binary[v] = 1;
    field.toggle(v, +1);
    if (c === v) break;
  }

  const proto = binary.slice();
  const protoField = new Float64Array(field.value);
  const rank = new Int32Array(N).fill(-1);

  // Phase 1 — strip minority pixels, ranking downward from the prototype count.
  {
    const b = proto.slice();
    const f = new Field();
    f.value.set(protoField);
    for (let r = initial - 1; r >= 0; r--) {
      const c = tightestCluster(b, f);
      b[c] = 0;
      f.toggle(c, -1);
      rank[c] = r;
    }
  }

  // Phase 2 — refill voids from the prototype up to half full.
  const b = proto.slice();
  const f = new Field();
  f.value.set(protoField);
  let r = initial;
  for (; r < N / 2; r++) {
    const v = largestVoid(b, f);
    b[v] = 1;
    f.toggle(v, +1);
    rank[v] = r;
  }

  // Phase 3 — past halfway the ZEROS are the minority, so keep filling their
  // tightest clusters; this keeps the upper half as evenly spread as the lower.
  const inv = new Uint8Array(N);
  for (; r < N; r++) {
    for (let i = 0; i < N; i++) inv[i] = b[i] ? 0 : 1;
    const invField = new Field();
    for (let i = 0; i < N; i++) if (inv[i]) invField.toggle(i, +1);
    const c = tightestCluster(inv, invField);
    b[c] = 1;
    rank[c] = r;
  }

  return rank;
}

async function main(): Promise<void> {
  const rank = build();
  const seen = new Set(rank);
  if (seen.size !== N || rank.some((v) => v < 0)) {
    throw new Error(`bake-blue-noise: ranks are not a permutation of 0..${N - 1}`);
  }

  const rows: string[] = [];
  for (let y = 0; y < SIZE; y++) {
    rows.push('  ' + Array.from(rank.slice(y * SIZE, y * SIZE + SIZE)).join(', ') + ',');
  }
  const out = `// GENERATED by \`npm run bake:blue-noise\` — do not edit by hand.
//
// Void-and-cluster blue-noise ranks, 0..${N - 1}, over a ${SIZE}x${SIZE} tile that
// repeats seamlessly. Divide by ${N} for a threshold in [0,1).
//
// Used to quantize photo zones: blue noise concentrates its error at high
// spatial frequency, which is invisible at the distance the panel is read,
// whereas Floyd-Steinberg's correlated error shows as worm texture.

export const BLUE_NOISE_SIZE = ${SIZE};

export const BLUE_NOISE_RANK: readonly number[] = [
${rows.join('\n')}
];
`;
  const dest = path.join(ROOT, 'src/image/blueNoise.generated.ts');
  await fs.writeFile(dest, out);
  console.log(`[bake-blue-noise] wrote ${path.relative(ROOT, dest)} (${SIZE}x${SIZE})`);
}

main().catch((err) => {
  console.error('[bake-blue-noise] failed:', err);
  process.exit(1);
});
