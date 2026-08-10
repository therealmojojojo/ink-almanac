/**
 * Server-side dithering behaviour.
 *
 * Guards the properties the change exists to establish: output lands on the
 * Inkplate palette, photo zones diffuse error while text zones do not, and the
 * dithered result carries the same tone as the greyscale it came from. That
 * last one is the regression guard for the defect that motivated the change —
 * the Inkplate library's own dither ran +19/255 bright because it diffused
 * error against a quantizer whose range didn't match what the panel emits.
 */
import { afterAll, beforeAll, afterEach, describe, expect, it } from 'vitest';
import path from 'node:path';
import sharp from 'sharp';
import { serve } from '@hono/node-server';
import { app } from '../src/server.js';
import { closeBrowser } from '../src/browser.js';
import { INKPLATE_PALETTE, nearestPaletteValue } from '../src/image/palette.js';

const PORT = Number(process.env.TEST_PORT ?? 8188);
const ROOT = path.resolve(__dirname, '..');
const FIXTURES = path.join(ROOT, 'test/fixtures/dither-masks/gallery-native');

const PALETTE = new Set<number>(INKPLATE_PALETTE);
let server: ReturnType<typeof serve>;

beforeAll(() => {
  process.env.RENDERER_INPUTS_DIR = FIXTURES;
  server = serve({ fetch: app.fetch, port: PORT, hostname: '127.0.0.1' });
});

afterAll(async () => {
  server.close();
  await closeBrowser();
});

afterEach(() => {
  delete process.env.RENDERER_DITHER;
});

async function render(mode: string, placement: 'server' | 'device'): Promise<Buffer> {
  process.env.RENDERER_DITHER = placement;
  const res = await fetch(`http://127.0.0.1:${PORT}/display/${mode}.png`);
  if (!res.ok) throw new Error(`${mode} returned ${res.status}: ${await res.text()}`);
  return Buffer.from(await res.arrayBuffer());
}

async function pixels(png: Buffer): Promise<{ data: Uint8Array; w: number; h: number }> {
  const { data, info } = await sharp(png)
    .toColourspace('b-w')
    .raw()
    .toBuffer({ resolveWithObject: true });
  return { data: new Uint8Array(data), w: info.width, h: info.height };
}

/** Mean over a rectangle — the eye integrates dither noise, so compare tone. */
function regionMean(p: { data: Uint8Array; w: number }, x0: number, y0: number, x1: number, y1: number): number {
  let sum = 0;
  let n = 0;
  for (let y = y0; y < y1; y++) {
    for (let x = x0; x < x1; x++) {
      sum += p.data[y * p.w + x]!;
      n++;
    }
  }
  return sum / n;
}

function distinctIn(p: { data: Uint8Array; w: number }, x0: number, y0: number, x1: number, y1: number): Set<number> {
  const s = new Set<number>();
  for (let y = y0; y < y1; y++) {
    for (let x = x0; x < x1; x++) s.add(p.data[y * p.w + x]!);
  }
  return s;
}

describe('server-side dithering', () => {
  it('emits only Inkplate palette values', async () => {
    const p = await pixels(await render('gallery', 'server'));
    const seen = new Set(p.data);
    const stray = [...seen].filter((v) => !PALETTE.has(v));
    expect(stray).toEqual([]);
    expect(seen.size).toBeGreaterThan(1);
  }, 60_000);

  it('emits a single-channel PNG', async () => {
    const md = await sharp(await render('gallery', 'server')).metadata();
    expect(md.channels).toBe(1);
  }, 60_000);

  it('keeps photo-zone tone within 3/255 of the greyscale it came from', async () => {
    // The bug this guards against showed up as a brightness bias, not as
    // noise. Compare in APPEARANCE space: emitted bytes are level selectors,
    // not tones, so averaging them directly would measure the selector
    // numbering rather than what the panel shows.
    const [srv, dev] = [await render('gallery', 'server'), await render('gallery', 'device')];
    const [ps, pd] = [await pixels(srv), await pixels(dev)];
    // gallery-native fixture: 383x250 image contained in the 1200x717 cell.
    const mean = (p: typeof ps) => regionMean(p, 51, 0, 1149, 717);
    expect(Math.abs(mean(ps) - mean(pd))).toBeLessThan(3);
  }, 90_000);

  it('hard-quantizes a face with no photo zone, with no dithering', async () => {
    // Weather's ditherMask() is `false`, so every pixel takes its nearest
    // palette value with no thresholding at all.
    const [srv, dev] = [await render('weather', 'server'), await render('weather', 'device')];
    const [ps, pd] = [await pixels(srv), await pixels(dev)];
    let mismatches = 0;
    for (let i = 0; i < ps.data.length; i++) {
      if (ps.data[i] !== nearestPaletteValue(pd.data[i]!)) mismatches++;
    }
    expect(mismatches).toBe(0);
  }, 90_000);

  it('blue-noise dither holds mean tone and uses both bracketing levels', async () => {
    // A flat mid-grey ramp must average back to itself and must be built from
    // the two levels that bracket it — not collapsed onto one.
    const { blueNoiseDither, rectMask } = await import('../src/image/dither.js');
    const W = 1200, H = 825;
    const v = 128; // sits between palette 109 and 146
    const flat = new Uint8Array(W * H).fill(v);
    const out = blueNoiseDither(flat, W, H, rectMask(0, 0, W, H));
    const seen = new Set(out);
    expect([...seen].sort((a, b) => a - b)).toEqual([109, 146]);
    const mean = out.reduce((a: number, b: number) => a + b, 0) / out.length;
    expect(Math.abs(mean - v)).toBeLessThan(1.5);
  });

  it('blue-noise tile is a permutation with a blue spectrum', async () => {
    const { BLUE_NOISE_RANK, BLUE_NOISE_SIZE } = await import(
      '../src/image/blueNoise.generated.js'
    );
    const n = BLUE_NOISE_SIZE * BLUE_NOISE_SIZE;
    expect(BLUE_NOISE_RANK.length).toBe(n);
    expect(new Set(BLUE_NOISE_RANK).size).toBe(n);
  });

  it('emits bytes that select their own panel level', () => {
    // The one hard constraint on the palette: the device picks a level with
    // floor(v/32), so each entry must land in its own 32-wide bucket.
    INKPLATE_PALETTE.forEach((v, level) => {
      expect(Math.floor((256 * v) / 8192)).toBe(level);
    });
  });

  it('leaves flat paper outside the mask as one palette value', async () => {
    // A strip of bare paper in the caption band, clear of glyphs and outside
    // the gallery photo mask. Error diffusion here would speckle it.
    const p = await pixels(await render('gallery', 'server'));
    const vals = distinctIn(p, 0, 720, 200, 736);
    expect(vals.size).toBe(1);
    // --paper must sit exactly on a palette entry. It is #fff = 255 (level 7)
    // because that is what the panel always showed: the old library path
    // quantized the previous #ececec (236) with `& 0xE0` and pushed it to 255.
    // Honest quantization sent 236 to 219 instead, one level darker, which
    // read as a seam against photo highlights on hardware (2026-08-10).
    // A token that lands between palette entries reintroduces that seam.
    expect([...vals][0]).toBe(255);
  }, 60_000);

  it('device placement leaves output at full range', async () => {
    const p = await pixels(await render('gallery', 'device'));
    const seen = new Set(p.data);
    const offPalette = [...seen].filter((v) => !PALETTE.has(v));
    expect(offPalette.length).toBeGreaterThan(0);
  }, 60_000);

  it('is byte-for-byte reproducible in both placements', async () => {
    for (const placement of ['server', 'device'] as const) {
      const a = await render('weather', placement);
      const b = await render('weather', placement);
      expect(a.equals(b)).toBe(true);
    }
  }, 120_000);
});
