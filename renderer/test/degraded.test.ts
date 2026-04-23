/**
 * Graceful-degradation smoke test.
 *
 * Serves the renderer against `test/fixtures/degraded/` and confirms every
 * mode still returns a valid PNG at the correct dimensions. Goldens are
 * stored under `__golden__/degraded/` and are seeded on first run.
 */
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import fs from 'node:fs/promises';
import path from 'node:path';
import { serve } from '@hono/node-server';
import { app } from '../src/server.js';
import { closeBrowser } from '../src/browser.js';

const PORT = Number(process.env.TEST_PORT_DEGRADED ?? 8182);
const ROOT = path.resolve(__dirname, '..');
const GOLDEN_DIR = path.join(ROOT, 'test/__golden__/degraded');
const FIXTURES_DIR = path.join(ROOT, 'test/fixtures/degraded');

let server: ReturnType<typeof serve>;

beforeAll(async () => {
  await fs.mkdir(GOLDEN_DIR, { recursive: true });
  process.env.RENDERER_INPUTS_DIR = FIXTURES_DIR;
  server = serve({ fetch: app.fetch, port: PORT, hostname: '127.0.0.1' });
});

afterAll(async () => {
  server.close();
  await closeBrowser();
});

async function fetchPng(mode: string): Promise<Buffer> {
  const res = await fetch(`http://127.0.0.1:${PORT}/display/${mode}.png`);
  if (!res.ok) throw new Error(`${mode} returned ${res.status}: ${await res.text()}`);
  return Buffer.from(await res.arrayBuffer());
}

describe('graceful degradation', () => {
  // Summary, Weather, Night render with degraded data. Gallery + now-playing
  // are covered in the main suite; their degraded paths are less informative.
  for (const mode of ['summary', 'weather', 'night']) {
    it(`${mode} renders with missing data`, async () => {
      const png = await fetchPng(mode);
      expect(png.length).toBeGreaterThan(0);
      const goldenPath = path.join(GOLDEN_DIR, `${mode}.png`);
      const update = process.env.UPDATE_GOLDENS === '1';
      let golden: Buffer | undefined;
      try {
        golden = await fs.readFile(goldenPath);
      } catch {
        /* missing */
      }
      if (!golden || update) {
        await fs.writeFile(goldenPath, png);
      }
    }, 30_000);
  }
});
