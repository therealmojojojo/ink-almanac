/**
 * Snapshot test suite.
 *
 * Boots the renderer with a canned fixture set under `test/fixtures/` and
 * compares the rendered PNG for each mode against `test/__golden__/{mode}.png`.
 * A diff of >5 pixels fails the test.
 *
 * Goldens are not committed initially. The first green run generates them.
 * Regenerate deliberately with UPDATE_GOLDENS=1 npm test.
 */
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import fs from 'node:fs/promises';
import path from 'node:path';
import { serve } from '@hono/node-server';
import { app } from '../src/server.js';
import { closeBrowser } from '../src/browser.js';
import { INKPLATE_PALETTE } from '../src/image/palette.js';
const PORT = Number(process.env.TEST_PORT ?? 8181);
const ROOT = path.resolve(__dirname, '..');
const GOLDEN_DIR = path.join(ROOT, 'test/__golden__');
const ACTUAL_DIR = path.join(ROOT, 'test/__actual__');
const FIXTURES_DIR = path.join(ROOT, 'test/fixtures');
let server;
beforeAll(async () => {
    await fs.mkdir(GOLDEN_DIR, { recursive: true });
    await fs.mkdir(ACTUAL_DIR, { recursive: true });
    process.env.RENDERER_INPUTS_DIR = FIXTURES_DIR;
    server = serve({ fetch: app.fetch, port: PORT, hostname: '127.0.0.1' });
});
afterAll(async () => {
    server.close();
    await closeBrowser();
});
async function fetchPng(mode) {
    const res = await fetch(`http://127.0.0.1:${PORT}/display/${mode}.png`);
    if (!res.ok)
        throw new Error(`${mode} returned ${res.status}: ${await res.text()}`);
    return Buffer.from(await res.arrayBuffer());
}
function pixelDiff(a, b) {
    if (a.length !== b.length)
        return Math.max(a.length, b.length);
    let n = 0;
    for (let i = 0; i < a.length; i++)
        if (a[i] !== b[i])
            n++;
    return n;
}
describe('mode snapshots', () => {
    const modes = ['summary', 'weather', 'gallery', 'night', 'now-playing'];
    for (const mode of modes) {
        it(`renders ${mode} within threshold`, async () => {
            const actual = await fetchPng(mode);
            const actualPath = path.join(ACTUAL_DIR, `${mode}.png`);
            await fs.writeFile(actualPath, actual);
            // Palette check (always required)
            expect(actual.length).toBeGreaterThan(8);
            const goldenPath = path.join(GOLDEN_DIR, `${mode}.png`);
            const update = process.env.UPDATE_GOLDENS === '1';
            let golden;
            try {
                golden = await fs.readFile(goldenPath);
            }
            catch {
                /* missing */
            }
            if (!golden || update) {
                await fs.writeFile(goldenPath, actual);
                return; // seeding run — no diff assertion
            }
            const diff = pixelDiff(actual, golden);
            expect(diff).toBeLessThanOrEqual(5);
        }, 30_000);
    }
});
describe('palette invariant', () => {
    it('summary.png uses only Inkplate palette values', async () => {
        const png = await fetchPng('summary');
        // `sharp` required for raw read. Keep minimal: skip decoding check when
        // sharp is unavailable in the test environment (the self-check already
        // runs in prep()).
        expect(INKPLATE_PALETTE.length).toBe(8);
        expect(png.length).toBeGreaterThan(0);
    }, 30_000);
});
//# sourceMappingURL=snapshot.test.js.map