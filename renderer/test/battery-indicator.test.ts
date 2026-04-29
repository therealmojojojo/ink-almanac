/**
 * Battery-indicator visibility test — asserts that every face carries a
 * non-em-dash battery label when `device.json` is present. Complements the
 * pixel-level snapshot check by making the requirement explicit and legible:
 * if the indicator regresses to `—` on any face, this fails cleanly with a
 * message naming the face rather than just "N pixels differ."
 *
 * Uses the HTML preview route (`/display/{mode}/preview`) rather than
 * rasterising — the indicator is emitted as `<span>82%</span>` inside a
 * `.battery-indicator` element; a text scan is sufficient.
 */
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import fs from 'node:fs/promises';
import path from 'node:path';
import { serve } from '@hono/node-server';
import { app } from '../src/server.js';
import { closeBrowser } from '../src/browser.js';

const ROOT = path.resolve(__dirname, '..');
const FIXTURES_DIR = path.join(ROOT, 'test/fixtures');

let server: ReturnType<typeof serve>;
let BASE: string;

beforeAll(async () => {
  process.env.RENDERER_INPUTS_DIR = FIXTURES_DIR;
  const port: number = await new Promise((resolve) => {
    server = serve({ fetch: app.fetch, port: 0, hostname: '127.0.0.1' }, (info) => {
      resolve(info.port);
    });
  });
  BASE = `http://127.0.0.1:${port}`;
});

afterAll(async () => {
  server.close();
  await closeBrowser();
});

async function previewHtml(mode: string): Promise<string> {
  const res = await fetch(`${BASE}/display/${mode}/preview`);
  if (!res.ok) throw new Error(`${mode} preview returned ${res.status}`);
  return res.text();
}

// The fixture device.json pins battery.percentage = 82.
const EXPECTED_LABEL = '82%';

// Night mode intentionally drops the battery indicator — the redesigned
// night face has its own minimal chrome (phrase, weekday, weather, caption)
// and battery state is not surfaced there. All other faces still carry it.
describe('battery indicator is populated on every face', () => {
  const modes = ['summary', 'weather', 'gallery', 'now-playing'];
  for (const mode of modes) {
    it(`${mode} shows ${EXPECTED_LABEL}`, async () => {
      const html = await previewHtml(mode);
      // Sanity: the battery container exists.
      expect(html).toContain('battery-indicator');
      // The real assertion: the percentage label, not an em-dash.
      expect(html).toContain(EXPECTED_LABEL);
      expect(html).not.toMatch(/<span>—<\/span>\s*<\/div>\s*<\/div>/); // em-dash fallback marker
    });
  }
});

describe('battery indicator degrades to em-dash when device.json is absent', () => {
  it('summary em-dashes without a device input', async () => {
    // Temporarily drop device.json from the in-scope directory by pointing
    // the renderer at a fixture subset without it (the degraded bundle).
    const degradedDir = path.join(ROOT, 'test/fixtures/degraded');
    const savedEnv = process.env.RENDERER_INPUTS_DIR;
    process.env.RENDERER_INPUTS_DIR = degradedDir;
    try {
      // Confirm degraded/device.json truly absent.
      const exists = await fs
        .stat(path.join(degradedDir, 'device.json'))
        .then(() => true)
        .catch(() => false);
      expect(exists).toBe(false);

      const res = await fetch(`${BASE}/display/summary/preview`);
      expect(res.status).toBe(200);
      const html = await res.text();
      expect(html).toContain('battery-indicator');
      // Graceful-degradation label is `—`; the 82% fixture label must NOT appear.
      expect(html).not.toContain(EXPECTED_LABEL);
      expect(html).toContain('—');
    } finally {
      process.env.RENDERER_INPUTS_DIR = savedEnv;
    }
  });
});
