/**
 * Integration test for `POST /inputs/:name`.
 *
 * Boots the renderer against a throwaway inputs directory, exercises the
 * auth / allow-list / size / JSON paths, and confirms that a successful
 * POST makes the new value visible to a subsequent `/display/*.png`.
 */
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { serve } from '@hono/node-server';
import { app } from '../src/server.js';
import { closeBrowser } from '../src/browser.js';

const TOKEN = 'test-token-abc';

let server: ReturnType<typeof serve>;
let workDir: string;
let BASE: string;

beforeAll(async () => {
  workDir = await fs.mkdtemp(path.join(os.tmpdir(), 'inkplate-inputs-'));
  // Seed the minimal set required by summary so we can exercise end-to-end.
  const fixtures = path.resolve(__dirname, 'fixtures');
  for (const name of ['clock', 'weather', 'news', 'pairing']) {
    const src = path.join(fixtures, `${name}.json`);
    const dst = path.join(workDir, `${name}.json`);
    await fs.copyFile(src, dst);
  }
  process.env.RENDERER_INPUTS_DIR = workDir;
  process.env.RENDERER_INPUT_TOKEN = TOKEN;
  // Bind to an ephemeral port; the `listening` callback gives us the real port
  // so we never collide with the other test files' servers.
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
  await fs.rm(workDir, { recursive: true, force: true });
});

async function post(name: string, body: string, opts: { token?: string } = {}): Promise<Response> {
  const headers: Record<string, string> = { 'content-type': 'application/json' };
  if (opts.token !== undefined) headers['authorization'] = `Bearer ${opts.token}`;
  return fetch(`${BASE}/inputs/${name}`, { method: 'POST', headers, body });
}

describe('POST /inputs/:name', () => {
  it('rejects missing auth with 401', async () => {
    const r = await post('clock', '{"time":"10:00","date":"x"}');
    expect(r.status).toBe(401);
  });

  it('rejects wrong token with 403', async () => {
    const r = await post('clock', '{"time":"10:00","date":"x"}', { token: 'wrong' });
    expect(r.status).toBe(403);
  });

  it('rejects name outside allow-list with 404', async () => {
    const r = await post('secret', '{}', { token: TOKEN });
    expect(r.status).toBe(404);
  });

  it('rejects invalid JSON with 400', async () => {
    const r = await post('clock', 'not-json', { token: TOKEN });
    expect(r.status).toBe(400);
  });

  it('rejects oversized body with 413', async () => {
    // 300 KB payload — over the 256 KB ceiling.
    const big = '{"x":"' + 'a'.repeat(300 * 1024) + '"}';
    const r = await post('clock', big, { token: TOKEN });
    expect(r.status).toBe(413);
  });

  it('writes atomically on success and reflects in subsequent render', async () => {
    const payload = JSON.stringify({ battery: { percentage: 13 } });
    const r = await post('device', payload, { token: TOKEN });
    expect(r.status).toBe(204);

    // File landed on disk with exact bytes.
    const onDisk = await fs.readFile(path.join(workDir, 'device.json'), 'utf8');
    expect(JSON.parse(onDisk)).toEqual({ battery: { percentage: 13 } });

    // Subsequent render picks it up. We don't rasterize (that's the snapshot
    // suite's job); preview HTML is enough to confirm the indicator renders
    // with the new value.
    const res = await fetch(`${BASE}/display/summary/preview`);
    expect(res.status).toBe(200);
    const html = await res.text();
    expect(html).toContain('13%');
  });
});
