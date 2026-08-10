/**
 * Snapshot test suite.
 *
 * Boots the renderer with a canned fixture set under `test/fixtures/` and
 * compares the rendered PNG for each mode against `test/__golden__/{mode}.png`
 * (device dither) and `{mode}.server.png` (server dither). More than 5
 * meaningfully-different pixels fails the test; see `pixelDiff`.
 *
 * Goldens are not committed initially. The first green run generates them.
 * Regenerate deliberately with UPDATE_GOLDENS=1 npm test.
 */
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import fs from 'node:fs/promises';
import path from 'node:path';
import sharp from 'sharp';
import { serve } from '@hono/node-server';
import { app } from '../src/server.js';
import { closeBrowser } from '../src/browser.js';
import { INKPLATE_PALETTE } from '../src/image/palette.js';

const PORT = Number(process.env.TEST_PORT ?? 8181);
const ROOT = path.resolve(__dirname, '..');
const GOLDEN_DIR = path.join(ROOT, 'test/__golden__');
const ACTUAL_DIR = path.join(ROOT, 'test/__actual__');
const FIXTURES_DIR = path.join(ROOT, 'test/fixtures');

let server: ReturnType<typeof serve>;

beforeAll(async () => {
  await fs.mkdir(GOLDEN_DIR, { recursive: true });
  await fs.mkdir(ACTUAL_DIR, { recursive: true });
  process.env.RENDERER_INPUTS_DIR = FIXTURES_DIR;
  // Pin the render instant so goldens stay valid across runs.
  process.env.INKPLATE_RENDER_NOW = '2026-08-10T14:00:00+03:00';
  server = serve({ fetch: app.fetch, port: PORT, hostname: '127.0.0.1' });
});

afterAll(async () => {
  server.close();
  await closeBrowser();
});

async function fetchPng(mode: string, placement: 'server' | 'device'): Promise<Buffer> {
  // Set explicitly rather than inherited: goldens are placement-specific, so a
  // suite that read the ambient RENDERER_DITHER would compare against the
  // wrong baseline whenever the default moves.
  process.env.RENDERER_DITHER = placement;
  const res = await fetch(`http://127.0.0.1:${PORT}/display/${mode}.png`);
  if (!res.ok) throw new Error(`${mode} returned ${res.status}: ${await res.text()}`);
  return Buffer.from(await res.arrayBuffer());
}

/**
 * Count meaningfully-different pixels between two renders.
 *
 * Compares DECODED pixels, not compressed PNG bytes. Byte comparison called
 * faces different when the images were visually identical: re-encoding and
 * Chromium's image decode jitter shift a couple of percent of pixels by 1-2
 * levels, which changes compressed length and swamped a 5-byte threshold.
 *
 * The +-8 tolerance is well below one panel level (the closest pair of
 * palette entries is 29 apart), so any real rendering change still registers
 * while decode noise does not.
 */
async function pixelDiff(a: Buffer, b: Buffer): Promise<number> {
  const [ra, rb] = await Promise.all([
    sharp(a).toColourspace('b-w').raw().toBuffer(),
    sharp(b).toColourspace('b-w').raw().toBuffer(),
  ]);
  if (ra.length !== rb.length) return Math.max(ra.length, rb.length);
  let n = 0;
  for (let i = 0; i < ra.length; i++) if (Math.abs(ra[i]! - rb[i]!) > 8) n++;
  return n;
}

describe('mode snapshots', () => {
  const modes = ['summary', 'weather', 'gallery', 'night', 'now-playing'];
  // Both dither placements get their own goldens. Without the `server` set,
  // no test would catch a face breaking under the path this change is moving
  // to — `dither.test.ts` checks properties, not appearance.
  const placements = ['device', 'server'] as const;
  for (const placement of placements) {
    const suffix = placement === 'device' ? '' : '.server';
    for (const mode of modes) {
      it(`renders ${mode} within threshold (${placement} dither)`, async () => {
        const actual = await fetchPng(mode, placement);
        await fs.writeFile(path.join(ACTUAL_DIR, `${mode}${suffix}.png`), actual);
        expect(actual.length).toBeGreaterThan(8);

        const goldenPath = path.join(GOLDEN_DIR, `${mode}${suffix}.png`);
        const update = process.env.UPDATE_GOLDENS === '1';
        let golden: Buffer | undefined;
        try {
          golden = await fs.readFile(goldenPath);
        } catch {
          /* missing */
        }
        if (!golden || update) {
          await fs.writeFile(goldenPath, actual);
          return; // seeding run — no diff assertion
        }
        const diff = await pixelDiff(actual, golden);
        expect(diff).toBeLessThanOrEqual(5);
      }, 30_000);
    }
  }
});

describe('palette invariant', () => {
  // Which values a render may contain depends on where dithering happens, so
  // the real per-pixel assertions live in `test/dither.test.ts`, which drives
  // both placements explicitly. This suite runs at the default placement and
  // only pins the palette definition the two sides agree on: the device maps
  // it with a bare floor(v/32), so the entries must stay 32 apart in level
  // terms and span the full range.
  it('palette maps 1:1 onto the panel levels 0-7', () => {
    expect(INKPLATE_PALETTE.length).toBe(8);
    expect(INKPLATE_PALETTE[0]).toBe(0);
    expect(INKPLATE_PALETTE[7]).toBe(255);
    INKPLATE_PALETTE.forEach((v, level) => {
      expect(Math.floor((256 * v) / 8192)).toBe(level); // RGB3BIT(v,v,v)
    });
  });
});
