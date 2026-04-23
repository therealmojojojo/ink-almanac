/**
 * Per-form snapshot tests for Gallery text-day.
 *
 * Renders one fixture per form value and freezes a golden PNG for each under
 * `test/__golden__/forms/<form>.png`. This catches silent regressions in
 * form-dispatch typography (e.g., a sonnet accidentally rendered as haiku).
 */
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import fs from 'node:fs/promises';
import path from 'node:path';
import { serve } from '@hono/node-server';
import { app } from '../src/server.js';
import { closeBrowser } from '../src/browser.js';

const PORT = Number(process.env.TEST_PORT_FORMS ?? 8183);
const ROOT = path.resolve(__dirname, '..');
const GOLDEN_DIR = path.join(ROOT, 'test/__golden__/forms');
const FIXTURES_ROOT = path.join(ROOT, 'test/fixtures/forms');

const FORMS = ['haiku', 'sonnet', 'free-verse', 'fragment', 'aphorism', 'quote'];

let server: ReturnType<typeof serve>;

beforeAll(async () => {
  await fs.mkdir(GOLDEN_DIR, { recursive: true });
  server = serve({ fetch: app.fetch, port: PORT, hostname: '127.0.0.1' });
});

afterAll(async () => {
  server.close();
  await closeBrowser();
});

async function renderForm(form: string): Promise<Buffer> {
  process.env.RENDERER_INPUTS_DIR = path.join(FIXTURES_ROOT, form);
  const res = await fetch(`http://127.0.0.1:${PORT}/display/gallery.png`);
  if (!res.ok) throw new Error(`${form} returned ${res.status}: ${await res.text()}`);
  return Buffer.from(await res.arrayBuffer());
}

describe('Gallery text-day form-dispatch', () => {
  for (const form of FORMS) {
    it(`renders ${form}`, async () => {
      const png = await renderForm(form);
      expect(png.length).toBeGreaterThan(0);
      const goldenPath = path.join(GOLDEN_DIR, `${form}.png`);
      const update = process.env.UPDATE_GOLDENS === '1';
      let golden: Buffer | undefined;
      try {
        golden = await fs.readFile(goldenPath);
      } catch {
        /* missing */
      }
      if (!golden || update) {
        await fs.writeFile(goldenPath, png);
        return;
      }
      // Binary diff byte count; 5-pixel threshold ≈ 40 bytes worth of drift
      // after palette quantization, conservatively.
      let diff = 0;
      for (let i = 0; i < Math.min(png.length, golden.length); i++) {
        if (png[i] !== golden[i]) diff++;
      }
      expect(diff).toBeLessThanOrEqual(80);
    }, 30_000);
  }
});
