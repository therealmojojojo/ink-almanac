import { serve } from '@hono/node-server';
import { Hono } from 'hono';
import fs from 'node:fs/promises';
import path from 'node:path';
import { randomUUID } from 'node:crypto';
import { z } from 'zod';
import { closeBrowser, ensureBrowser, isBrowserReady } from './browser.js';
import { MODES, PORT, HOST, ROOT, TEMPLATES_DIR, inputsDir, isMode, type Mode } from './config.js';
import { log } from './logger.js';
import { MissingInputError, prepareMode } from './modes/index.js';
import {
  prepareDelightTest,
  predictAnthologyWidth,
  listBilingualHaiku,
  prepareSmartPillTest,
  prepareTextSummaryTest,
  predictSmartPillFit,
  listSmartPillTexts,
  prepareFaceTest,
  predictAllTriplets,
  dominanceFilter,
  type FaceTestParams,
} from './modes/debugDelight.js';
import { renderToPng, type ClockZone } from './render.js';
import { VerseOverflowError } from './zoneApply.js';
import { enrichFromSonos } from './enrichment/index.js';

/** Input names that `POST /inputs/:name` will accept. Matches the canonical
 *  set every face mode can consume; rejects everything else with 404 so the
 *  endpoint isn't a generic file-drop. */
const WRITABLE_INPUTS = new Set([
  'clock',
  'weather',
  'news',
  'pairing',
  'sonos',
  'device',
]);
const INPUT_NAME_RE = /^[a-z0-9_-]+$/;
const MAX_INPUT_BYTES = 256 * 1024;

const app = new Hono();

/*
 * Per-render HTML cache. Populated when /display/:mode.png prepares a mode;
 * Playwright then navigates to /internal/html/:sid to fetch the HTML over HTTP
 * so relative /static and /inputs URLs resolve against this server.
 */
const htmlByToken = new Map<string, string>();

/*
 * Most-recent clock-zone bbox per mode, populated on every PNG render and
 * served by `/display/:mode/clock-zone.json`. The device firmware fetches
 * this on every Full wake to position its 1-bit partial-update digits at
 * the exact same pixel coordinates the renderer painted, regardless of
 * which mode/variant rendered. Map is in-memory and survives only while
 * the renderer process runs — the firmware refreshes it on next Full wake.
 */
const clockZoneByMode = new Map<string, ClockZone>();

app.get('/healthz', (c) =>
  c.json({ status: 'ok', playwright_ready: isBrowserReady() }, 200),
);

// --- Static assets (CSS + fonts + inputs dir) --------------------------------

async function serveFile(rel: string): Promise<Response> {
  const full = path.join(ROOT, rel);
  try {
    const data = await fs.readFile(full);
    const ext = path.extname(full).toLowerCase();
    const type =
      ext === '.css'
        ? 'text/css; charset=utf-8'
        : ext === '.woff2'
          ? 'font/woff2'
          : ext === '.png'
            ? 'image/png'
            : ext === '.jpg' || ext === '.jpeg'
              ? 'image/jpeg'
              : ext === '.json'
                ? 'application/json; charset=utf-8'
                : 'application/octet-stream';
    return new Response(data as unknown as BodyInit, {
      status: 200,
      headers: { 'content-type': type, 'cache-control': 'no-store' },
    });
  } catch (err) {
    if ((err as NodeJS.ErrnoException).code === 'ENOENT') {
      return new Response('not found', { status: 404 });
    }
    throw err;
  }
}

app.get('/static/css/tokens.css', () =>
  serveFile('templates/shared/tokens.css'),
);
app.get('/static/css/fonts.css', () => serveFile('templates/shared/fonts.css'));
app.get('/static/css/layout.css', () => serveFile('templates/shared/layout.css'));
app.get('/static/icons.svg', () => serveFile('templates/shared/icons.svg'));
app.get('/static/css/:file', (c) => {
  const file = c.req.param('file');
  // Accept summary.css, weather.css, gallery.css, night.css, now-playing.css,
  // gallery-visual.css, gallery-text.css.
  const stem = file.replace(/\.css$/, '');
  return serveFile(path.join('templates', stem, file));
});
app.get('/static/fonts/:file', (c) =>
  serveFile(path.join('templates/fonts', c.req.param('file'))),
);
// Per-mode image assets (e.g., now-playing fallback art when Sonos's art_url
// fails to load). URL shape mirrors the CSS route's stem→template-dir
// convention: /static/img/<mode>/<file> → templates/<mode>/<file>.
app.get('/static/img/:mode/:file', (c) =>
  serveFile(path.join('templates', c.req.param('mode'), c.req.param('file'))),
);
app.get('/inputs/:file', (c) =>
  serveFile(path.join('inputs', c.req.param('file'))),
);

// --- HA proxy (narrow, safe): /ha-proxy/api/media_player_proxy/... -----------
//
// Chromium running inside Playwright on this Mac can't reach the HA LAN IP
// directly (an application-layer firewall blocks Node/Chromium while allowing
// curl). To keep album art working, rewrite the Sonos entity_picture URL into
// a same-origin path and proxy only the exact HA sub-surface we need.
//
// The entity_picture URL carries its own `token=...` query param, but as of
// HA 2025.x the `/api/media_player_proxy/...` endpoint also requires a real
// bearer auth token — without it, the request hangs to its server-side
// timeout. We attach `ha_long_lived_token` from ha/secrets.yaml. We only
// allow the media_player_proxy path to avoid turning this into a general
// HA bypass.
app.get('/ha-proxy/api/media_player_proxy/:rest{.+}', async (c) => {
  // Resolve HA base URL + long-lived token from ha/secrets.yaml (same source
  // as sim.ts).
  const haSecrets = path.resolve(ROOT, '..', 'ha', 'secrets.yaml');
  let haBase = '';
  let haToken = '';
  try {
    const content = await fs.readFile(haSecrets, 'utf-8');
    const baseMatch = content.match(/^ha_base_url:\s*"?([^"\n]+?)"?\s*$/m);
    if (baseMatch?.[1]) haBase = baseMatch[1].trim();
    const tokenMatch = content.match(/^ha_long_lived_token:\s*"?([^"\n]+?)"?\s*$/m);
    if (tokenMatch?.[1]) haToken = tokenMatch[1].trim();
  } catch {
    // fall through; empty haBase yields 502 below
  }
  if (!haBase) return c.text('ha_base_url not configured\n', 502);
  if (!haToken) return c.text('ha_long_lived_token not configured\n', 502);

  // Reconstruct the full target URL. We preserve any query params (token).
  const rest = c.req.param('rest');
  const url = new URL(c.req.url);
  const target = `${haBase.replace(/\/+$/, '')}/api/media_player_proxy/${rest}${url.search}`;

  // Shell out to curl — Node's fetch can't reach HA on this host.
  // --max-time is intentionally short (2 s): when HA's media_player_proxy
  // upstream hangs (Sonos `getaa` failing for some Spotify tracks), the
  // happy-path fetch succeeds in ~50 ms on LAN, so anything past 2 s is
  // already a failure. Returning a 502 quickly lets the renderer's
  // now-playing template's `<img onerror>` fall back to the local fallback
  // art well within the device's 3 s HTTP budget for the whole PNG render.
  // Without this, slow upstream renders pushed total render time past the
  // device's timeout, causing back-to-back failed Full draws and a multi-
  // minute panel freeze.
  const { spawn } = await import('node:child_process');
  return new Promise<Response>((resolve) => {
    const child = spawn('curl', [
      '-s', '--max-time', '2',
      '-o', '-',
      '-D', '-', // headers to stdout, separated from body by blank line
      '-H', `Authorization: Bearer ${haToken}`,
      target,
    ]);
    const chunks: Buffer[] = [];
    child.stdout.on('data', (b) => chunks.push(b));
    child.on('close', (code) => {
      if (code !== 0) {
        resolve(new Response(`curl exit ${code}\n`, { status: 502 }));
        return;
      }
      const buf = Buffer.concat(chunks);
      // Split headers from body at the first \r\n\r\n.
      const sep = Buffer.from('\r\n\r\n');
      const idx = buf.indexOf(sep);
      if (idx < 0) {
        resolve(new Response(buf, { status: 200 }));
        return;
      }
      const headerText = buf.slice(0, idx).toString('utf8');
      const body = buf.slice(idx + sep.length);
      const statusMatch = headerText.match(/^HTTP\/[\d.]+ (\d{3})/);
      const status = statusMatch ? parseInt(statusMatch[1]!, 10) : 200;
      const ctMatch = headerText.match(/^content-type:\s*(.+)$/im);
      const headers: Record<string, string> = {};
      if (ctMatch?.[1]) headers['content-type'] = ctMatch[1].trim();
      resolve(new Response(body, { status, headers }));
    });
    child.on('error', () =>
      resolve(new Response('curl spawn failed\n', { status: 502 })),
    );
  });
});

// --- Internal: HTML payload Playwright fetches --------------------------------

app.get('/internal/html/:token', (c) => {
  const html = htmlByToken.get(c.req.param('token'));
  if (!html) return c.text('not found', 404);
  return new Response(html, {
    status: 200,
    headers: { 'content-type': 'text/html; charset=utf-8' },
  });
});

// --- Preview: human-facing, same HTML but not consumed by Playwright ---------

app.get('/display/:mode/preview', async (c) => {
  const mode = c.req.param('mode');
  if (!isMode(mode)) return c.text(notFoundBody(mode), 404);
  try {
    const variant = c.req.query('variant');
    const prepared = await prepareMode(mode, { variant });
    return new Response(prepared.html, {
      status: 200,
      headers: { 'content-type': 'text/html; charset=utf-8' },
    });
  } catch (err) {
    return mapError(err, c);
  }
});

// --- Main render endpoint ----------------------------------------------------

app.get('/display/:file', async (c) => {
  const file = c.req.param('file');
  const m = /^([a-z-]+)\.png$/.exec(file);
  if (!m) return c.text(notFoundBody(file), 404);
  const mode = m[1]!;
  if (!isMode(mode)) return c.text(notFoundBody(mode), 404);

  try {
    const variant = c.req.query('variant');
    const prepared = await prepareMode(mode as Mode, { variant });
    const token = randomUUID();
    htmlByToken.set(token, prepared.html);
    try {
      // Use the request's own origin so Playwright reaches the same server,
      // regardless of what RENDERER_PORT the server started on (important
      // for tests that use randomized ports).
      const origin = new URL(c.req.url).origin.replace(/^http:\/\/0\.0\.0\.0/, 'http://127.0.0.1');
      const url = `${origin}/internal/html/${token}`;
      const result = await renderToPng({ url, dither: prepared.dither });
      if (result.clockZone) {
        clockZoneByMode.set(mode, result.clockZone);
      } else {
        clockZoneByMode.delete(mode);
      }
      const headers: Record<string, string> = {
        'content-type': 'image/png',
        'content-length': String(result.png.length),
        'cache-control': 'no-store',
        'x-render-mode': mode,
      };
      if (result.clockZone) {
        const z = result.clockZone;
        headers['x-clock-zone'] =
          `x=${z.x} y=${z.y} w=${z.w} h=${z.h} font_size=${z.font_size}`;
      }
      return new Response(result.png as unknown as BodyInit, {
        status: 200,
        headers,
      });
    } finally {
      htmlByToken.delete(token);
    }
  } catch (err) {
    return mapError(err, c);
  }
});

// --- Debug: bilingual delight cell at custom font sizes ----------------------
//
// Spot-check tool for the haiku/tanka anthology layout. Loads a corpus text
// directly and renders the full Summary face with that haiku in the delight
// cell at the supplied JA/EN sizes. Not part of the production face rotation.
//
//   GET /debug/delight-test/preview?id=<haiku-id>&ja=32&en=30 [&lh=56]   → HTML
//   GET /debug/delight-test.png?id=<haiku-id>&ja=32&en=30 [&lh=56]       → PNG

function parseDelightTestQuery(c: { req: { query: (k: string) => string | undefined } }) {
  const id = c.req.query('id');
  if (!id) throw new Error("missing required query param 'id'");
  const num = (k: string, fallback: number) => {
    const v = c.req.query(k);
    if (v == null) return fallback;
    const n = Number(v);
    if (!Number.isFinite(n) || n <= 0) throw new Error(`'${k}' must be a positive number`);
    return n;
  };
  const out: { id: string; jaSize: number; enSize: number; lineHeight?: number } = {
    id,
    jaSize: num('ja', 32),
    enSize: num('en', 30),
  };
  if (c.req.query('lh') != null) out.lineHeight = num('lh', 56);
  return out;
}

app.get('/debug/delight-test/preview', async (c) => {
  try {
    const opts = parseDelightTestQuery(c);
    const prepared = await prepareDelightTest(opts);
    return new Response(prepared.html, {
      status: 200,
      headers: { 'content-type': 'text/html; charset=utf-8' },
    });
  } catch (err) {
    return mapError(err, c);
  }
});

// Grid view: every bilingual haiku predicted to overflow at the requested
// sizes, each rendered live in an iframe so the operator can scroll through
// and judge readability in one pass.
//
//   GET /debug/delight-test/all?ja=32&en=30           → just the overflow set
//   GET /debug/delight-test/all?ja=32&en=30&all=1     → all bilingual haiku
//   GET /debug/delight-test/all?ja=32&en=30&margin=20 → also includes any
//     haiku that fit within `margin` u of the 609u budget (borderline checks)
app.get('/debug/delight-test/all', async (c) => {
  try {
    const ja = Number(c.req.query('ja') ?? 32);
    const en = Number(c.req.query('en') ?? 30);
    const lh = c.req.query('lh') != null ? Number(c.req.query('lh')) : undefined;
    const showAll = c.req.query('all') === '1';
    const margin = Number(c.req.query('margin') ?? 0);
    if (!Number.isFinite(ja) || ja <= 0) throw new Error("'ja' must be a positive number");
    if (!Number.isFinite(en) || en <= 0) throw new Error("'en' must be a positive number");

    const haiku = await listBilingualHaiku();
    const rows = haiku.map((h) => {
      const w = predictAnthologyWidth(h.ja, h.en, ja, en);
      return { h, ...w, over: w.width - w.budget };
    });
    const filtered = showAll
      ? rows
      : rows.filter((r) => r.over > -margin || r.lineMismatch);
    filtered.sort((a, b) => b.over - a.over);

    const lhParam = lh ? `&lh=${lh}` : '';
    const cards = filtered.map((r) => {
      const previewUrl = `/debug/delight-test/preview?id=${encodeURIComponent(r.h.id)}&ja=${ja}&en=${en}${lhParam}`;
      const verdict = r.lineMismatch
        ? `<span class="bad">LINE MISMATCH</span> ja=${r.h.ja.split('\n').filter(Boolean).length} en=${r.h.en.split('\n').filter(Boolean).length}`
        : r.over > 0
          ? `<span class="bad">+${r.over}u over</span>`
          : `<span class="ok">${-r.over}u to spare</span>`;
      return `
<section class="card">
  <header>
    <h2>${r.h.id}</h2>
    <div class="meta">
      <span>form: ${r.h.form}</span>
      <span>JA max: ${r.ja_max} · EN max: ${r.en_max}</span>
      <span>predicted: ${r.width}u / ${r.budget}u</span>
      ${verdict}
      <span><a href="${previewUrl}" target="_blank">open</a></span>
    </div>
  </header>
  <iframe loading="lazy" src="${previewUrl}" width="1200" height="825"></iframe>
</section>`;
    }).join('\n');

    const summary = `Sizes: JA=${ja}u · EN=${en}u${lh ? ` · LH=${lh}u` : ''}. ` +
      `Showing ${filtered.length} of ${rows.length} bilingual haiku/tanka` +
      (showAll ? ' (all).' : margin > 0 ? ` (overflow + within ${margin}u of budget).` : ' (overflow only).');

    const page = `<!doctype html>
<html><head><meta charset="utf-8">
<title>Delight overflow grid · ja=${ja} en=${en}</title>
<style>
  body { margin: 0; font-family: -apple-system, BlinkMacSystemFont, sans-serif; background: #f4f4f4; color: #222; }
  .summary { position: sticky; top: 0; background: #fff; border-bottom: 1px solid #ddd; padding: 12px 24px; z-index: 10; }
  .summary form { display: inline-flex; gap: 12px; align-items: center; margin-left: 24px; font-size: 13px; }
  .summary input[type=number] { width: 60px; }
  .card { margin: 24px auto; width: 1200px; background: #fff; box-shadow: 0 1px 3px rgba(0,0,0,.1); }
  .card header { padding: 12px 16px; border-bottom: 1px solid #eee; display: flex; flex-direction: column; gap: 4px; }
  .card h2 { margin: 0; font-size: 16px; font-family: ui-monospace, SFMono-Regular, monospace; }
  .card .meta { display: flex; gap: 16px; font-size: 12px; color: #666; flex-wrap: wrap; }
  .card .meta .bad { color: #b00; font-weight: 600; }
  .card .meta .ok { color: #060; }
  .card iframe { display: block; border: 0; }
</style>
</head><body>
<div class="summary">
  <strong>Delight overflow grid</strong>
  <span style="margin-left:12px;color:#666">${summary}</span>
  <form method="get" action="/debug/delight-test/all">
    JA <input name="ja" type="number" value="${ja}" min="20" max="60">
    EN <input name="en" type="number" value="${en}" min="20" max="60">
    LH <input name="lh" type="number" value="${lh ?? ''}" placeholder="56">
    margin <input name="margin" type="number" value="${margin}" min="0" max="200">
    <label><input name="all" type="checkbox" value="1" ${showAll ? 'checked' : ''}> all</label>
    <button type="submit">apply</button>
  </form>
</div>
${cards || '<p style="padding:48px;text-align:center;color:#666">No haiku in the requested set.</p>'}
</body></html>`;
    return new Response(page, { status: 200, headers: { 'content-type': 'text/html; charset=utf-8' } });
  } catch (err) {
    return mapError(err, c);
  }
});

app.get('/debug/delight-test.png', async (c) => {
  try {
    const opts = parseDelightTestQuery(c);
    const prepared = await prepareDelightTest(opts);
    const token = randomUUID();
    htmlByToken.set(token, prepared.html);
    try {
      const origin = new URL(c.req.url).origin.replace(/^http:\/\/0\.0\.0\.0/, 'http://127.0.0.1');
      const url = `${origin}/internal/html/${token}`;
      const result = await renderToPng({ url, dither: prepared.dither });
      return new Response(result.png as unknown as BodyInit, {
        status: 200,
        headers: {
          'content-type': 'image/png',
          'content-length': String(result.png.length),
          'cache-control': 'no-store',
          'x-render-mode': 'debug:delight-test',
          'x-delight-id': opts.id,
          'x-delight-sizes': `ja=${opts.jaSize} en=${opts.enSize}`,
        },
      });
    } finally {
      htmlByToken.delete(token);
    }
  } catch (err) {
    return mapError(err, c);
  }
});

// --- Debug: smart-pill cell at custom size / line-height / padding ----------
//
//   GET /debug/smart-pill-test/preview?id=<text-id>&size=30&lh=1.35&pad=1   → HTML
//   GET /debug/smart-pill-test.png?id=<text-id>&size=30&lh=1.35&pad=1       → PNG
//   GET /debug/smart-pill-test/all?size=30&lh=1.35&pad=1                    → grid
//
// Loads `smart_pill.body` from a corpus text and renders the full Summary
// face with that body in the pill cell at the supplied geometry. `pad=0`
// strips the cell's bottom padding and top-aligns the body (vs. the
// production vertical-center) — the same toggle the audit model uses.

function parseSmartPillQuery(c: { req: { query: (k: string) => string | undefined } }) {
  const id = c.req.query('id');
  if (!id) throw new Error("missing required query param 'id'");
  const num = (k: string, fallback: number, allowFloat = false) => {
    const v = c.req.query(k);
    if (v == null) return fallback;
    const n = Number(v);
    if (!Number.isFinite(n) || n <= 0) throw new Error(`'${k}' must be a positive number`);
    if (!allowFloat && !Number.isInteger(n)) throw new Error(`'${k}' must be an integer`);
    return n;
  };
  return {
    id,
    size: num('size', 30),
    lineHeight: num('lh', 1.35, true),
    pad: c.req.query('pad') !== '0',
  };
}

app.get('/debug/smart-pill-test/preview', async (c) => {
  try {
    const opts = parseSmartPillQuery(c);
    const prepared = await prepareSmartPillTest(opts);
    return new Response(prepared.html, {
      status: 200,
      headers: { 'content-type': 'text/html; charset=utf-8' },
    });
  } catch (err) {
    return mapError(err, c);
  }
});

app.get('/debug/smart-pill-test.png', async (c) => {
  try {
    const opts = parseSmartPillQuery(c);
    const prepared = await prepareSmartPillTest(opts);
    const token = randomUUID();
    htmlByToken.set(token, prepared.html);
    try {
      const origin = new URL(c.req.url).origin.replace(/^http:\/\/0\.0\.0\.0/, 'http://127.0.0.1');
      const url = `${origin}/internal/html/${token}`;
      const result = await renderToPng({ url, dither: prepared.dither });
      return new Response(result.png as unknown as BodyInit, {
        status: 200,
        headers: {
          'content-type': 'image/png',
          'content-length': String(result.png.length),
          'cache-control': 'no-store',
          'x-render-mode': 'debug:smart-pill-test',
          'x-pill-id': opts.id,
          'x-pill-params': `size=${opts.size} lh=${opts.lineHeight} pad=${opts.pad ? 1 : 0}`,
        },
      });
    } finally {
      htmlByToken.delete(token);
    }
  } catch (err) {
    return mapError(err, c);
  }
});

// Render the production summary face for a single corpus text id —
// delight cell shows the body, pill cell shows that text's smart_pill.
// Used by the truncation-audit review page (a one-glance view of the text
// the device would show when this item is the daily summary).
app.get('/debug/text-summary-test/preview', async (c) => {
  try {
    const id = c.req.query('id');
    if (!id) throw new Error("missing required query param 'id'");
    const prepared = await prepareTextSummaryTest(id);
    return new Response(prepared.html, {
      status: 200,
      headers: { 'content-type': 'text/html; charset=utf-8' },
    });
  } catch (err) {
    return mapError(err, c);
  }
});

app.get('/debug/text-summary-test.png', async (c) => {
  try {
    const id = c.req.query('id');
    if (!id) throw new Error("missing required query param 'id'");
    const prepared = await prepareTextSummaryTest(id);
    const token = randomUUID();
    htmlByToken.set(token, prepared.html);
    try {
      const origin = new URL(c.req.url).origin.replace(/^http:\/\/0\.0\.0\.0/, 'http://127.0.0.1');
      const url = `${origin}/internal/html/${token}`;
      const result = await renderToPng({ url, dither: prepared.dither });
      return new Response(result.png as unknown as BodyInit, {
        status: 200,
        headers: {
          'content-type': 'image/png',
          'content-length': String(result.png.length),
          'cache-control': 'no-store',
          'x-render-mode': 'debug:text-summary-test',
          'x-text-id': id,
        },
      });
    } finally {
      htmlByToken.delete(token);
    }
  } catch (err) {
    return mapError(err, c);
  }
});

app.get('/debug/smart-pill-test/all', async (c) => {
  try {
    const size = Number(c.req.query('size') ?? 30);
    const lh = Number(c.req.query('lh') ?? 1.35);
    const pad = c.req.query('pad') !== '0';
    const showAll = c.req.query('all') === '1';
    const margin = Number(c.req.query('margin') ?? 0);
    if (!Number.isFinite(size) || size <= 0) throw new Error("'size' must be a positive number");
    if (!Number.isFinite(lh) || lh <= 0) throw new Error("'lh' must be a positive number");

    const texts = await listSmartPillTexts();
    const rows = texts.map((t) => {
      const fit = predictSmartPillFit(t.body, { size, lineHeight: lh, pad });
      return { t, ...fit };
    });
    const filtered = showAll
      ? rows
      : rows.filter((r) => r.over > -margin);
    filtered.sort((a, b) => b.over - a.over);

    const padQ = pad ? '1' : '0';
    const cards = filtered.map((r) => {
      const previewUrl = `/debug/smart-pill-test/preview?id=${encodeURIComponent(r.t.id)}&size=${size}&lh=${lh}&pad=${padQ}`;
      const verdict = r.overflow
        ? `<span class="bad">+${r.over} chars over (${r.chars}/${r.capacity})</span>`
        : `<span class="ok">${-r.over} chars to spare (${r.chars}/${r.capacity})</span>`;
      return `
<section class="card">
  <header>
    <h2>${r.t.id}</h2>
    <div class="meta">
      <span>chars: ${r.chars}</span>
      <span>cap: ${r.charsPerLine}/line × ${r.rows} rows = ${r.capacity}</span>
      ${verdict}
      <span><a href="${previewUrl}" target="_blank">open</a></span>
    </div>
  </header>
  <iframe loading="lazy" src="${previewUrl}" width="1200" height="825"></iframe>
</section>`;
    }).join('\n');

    const summaryLine = `Sizes: size=${size}u · lh=${lh} · pad=${padQ}. ` +
      `Showing ${filtered.length} of ${rows.length} texts with smart_pill.body` +
      (showAll ? ' (all).' : margin > 0 ? ` (overflow + within ${margin} chars of capacity).` : ' (overflow only).');

    const page = `<!doctype html>
<html><head><meta charset="utf-8">
<title>Smart-pill overflow grid · size=${size} lh=${lh} pad=${padQ}</title>
<style>
  body { margin: 0; font-family: -apple-system, BlinkMacSystemFont, sans-serif; background: #f4f4f4; color: #222; }
  .summary { position: sticky; top: 0; background: #fff; border-bottom: 1px solid #ddd; padding: 12px 24px; z-index: 10; }
  .summary form { display: inline-flex; gap: 12px; align-items: center; margin-left: 24px; font-size: 13px; }
  .summary input[type=number], .summary input[type=text] { width: 70px; }
  .card { margin: 24px auto; width: 1200px; background: #fff; box-shadow: 0 1px 3px rgba(0,0,0,.1); }
  .card header { padding: 12px 16px; border-bottom: 1px solid #eee; display: flex; flex-direction: column; gap: 4px; }
  .card h2 { margin: 0; font-size: 16px; font-family: ui-monospace, SFMono-Regular, monospace; }
  .card .meta { display: flex; gap: 16px; font-size: 12px; color: #666; flex-wrap: wrap; }
  .card .meta .bad { color: #b00; font-weight: 600; }
  .card .meta .ok { color: #060; }
  .card iframe { display: block; border: 0; }
</style>
</head><body>
<div class="summary">
  <strong>Smart-pill overflow grid</strong>
  <span style="margin-left:12px;color:#666">${summaryLine}</span>
  <form method="get" action="/debug/smart-pill-test/all">
    size <input name="size" type="number" value="${size}" min="16" max="48">
    lh <input name="lh" type="text" value="${lh}">
    pad <select name="pad"><option value="1" ${pad ? 'selected' : ''}>1</option><option value="0" ${!pad ? 'selected' : ''}>0</option></select>
    margin <input name="margin" type="number" value="${margin}" min="0" max="2000">
    <label><input name="all" type="checkbox" value="1" ${showAll ? 'checked' : ''}> all</label>
    <button type="submit">apply</button>
  </form>
</div>
${cards || '<p style="padding:48px;text-align:center;color:#666">No texts in the requested set.</p>'}
</body></html>`;
    return new Response(page, { status: 200, headers: { 'content-type': 'text/html; charset=utf-8' } });
  } catch (err) {
    return mapError(err, c);
  }
});

// --- Debug: unified face test (per-triplet, all params, dominance grid) -----
//
//   GET /debug/face-test/preview?triplet=<id>&...params       → HTML
//   GET /debug/face-test.png?triplet=<id>&...params           → PNG
//   GET /debug/face-test/all?...params [&margin=N] [&all=1]   → grid
//
// Each card on the grid is one corpus triplet, rendered with that triplet's
// real summary-slot text:
//   - delight cell  = summary-slot text body (visual-day only)
//   - pill cell     = summary-slot text's smart_pill.body (every triplet)
//
// Default grid filters to the dominance frontier of the overflow set (per
// zone shape: pill / bilingual delight / monolingual delight). If those
// dominators all fit at current params, every other triplet fits too.

function parseFaceParams(c: { req: { query: (k: string) => string | undefined } }): FaceTestParams {
  const num = (k: string, fallback: number, allowFloat = false) => {
    const v = c.req.query(k);
    if (v == null || v === '') return fallback;
    const n = Number(v);
    if (!Number.isFinite(n)) throw new Error(`'${k}' must be a number`);
    if (!allowFloat && !Number.isInteger(n)) throw new Error(`'${k}' must be an integer`);
    return n;
  };
  const out: FaceTestParams = {
    jaSize: num('ja', 32),
    enSize: num('en', 30),
    pillSize: num('pill_size', 30),
    pillLineHeight: num('pill_lh', 1.35, true),
    pillPad: c.req.query('pill_pad') !== '0',
    pillGrowU: num('pill_grow_u', 0),
  };
  const ds = c.req.query('delight_size');
  if (ds != null && ds !== '') {
    const n = Number(ds);
    if (!Number.isFinite(n) || n <= 0) throw new Error("'delight_size' must be a positive number");
    out.delightSize = n;
  }
  if (out.jaSize <= 0 || out.enSize <= 0 || out.pillSize <= 0 || out.pillLineHeight <= 0) {
    throw new Error('font-size / line-height params must be positive');
  }
  return out;
}

app.get('/debug/face-test/preview', async (c) => {
  try {
    const id = c.req.query('triplet');
    if (!id) throw new Error("missing required query param 'triplet'");
    const params = parseFaceParams(c);
    const prepared = await prepareFaceTest(id, params);
    return new Response(prepared.html, {
      status: 200,
      headers: { 'content-type': 'text/html; charset=utf-8' },
    });
  } catch (err) {
    return mapError(err, c);
  }
});

app.get('/debug/face-test.png', async (c) => {
  try {
    const id = c.req.query('triplet');
    if (!id) throw new Error("missing required query param 'triplet'");
    const params = parseFaceParams(c);
    const prepared = await prepareFaceTest(id, params);
    const token = randomUUID();
    htmlByToken.set(token, prepared.html);
    try {
      const origin = new URL(c.req.url).origin.replace(/^http:\/\/0\.0\.0\.0/, 'http://127.0.0.1');
      const url = `${origin}/internal/html/${token}`;
      const result = await renderToPng({ url, dither: prepared.dither });
      return new Response(result.png as unknown as BodyInit, {
        status: 200,
        headers: {
          'content-type': 'image/png',
          'content-length': String(result.png.length),
          'cache-control': 'no-store',
          'x-render-mode': 'debug:face-test',
          'x-triplet': id,
        },
      });
    } finally {
      htmlByToken.delete(token);
    }
  } catch (err) {
    return mapError(err, c);
  }
});

app.get('/debug/face-test/all', async (c) => {
  try {
    const params = parseFaceParams(c);
    const margin = Number(c.req.query('margin') ?? 0);
    const showAll = c.req.query('all') === '1';
    if (!Number.isFinite(margin) || margin < 0) throw new Error("'margin' must be ≥ 0");

    const all = await predictAllTriplets(params);
    const universe = all.length;
    const overflowing = all.filter((r) => r.anyOverflow);
    const filtered = showAll ? all : dominanceFilter(all, margin);

    // Sort: delight overflows first, then pill overflows; within each, worst over budget.
    filtered.sort((a, b) => {
      const aw = (a.delight?.overflow ? 1 : 0) + (a.pill?.overflow ? 1 : 0);
      const bw = (b.delight?.overflow ? 1 : 0) + (b.pill?.overflow ? 1 : 0);
      if (aw !== bw) return bw - aw;
      const aOver =
        (a.delight && 'width' in a.delight ? a.delight.width - a.delight.budget : 0) +
        (a.pill ? Math.max(0, a.pill.chars - a.pill.capacity) : 0);
      const bOver =
        (b.delight && 'width' in b.delight ? b.delight.width - b.delight.budget : 0) +
        (b.pill ? Math.max(0, b.pill.chars - b.pill.capacity) : 0);
      return bOver - aOver;
    });

    const qs = new URLSearchParams();
    qs.set('ja', String(params.jaSize));
    qs.set('en', String(params.enSize));
    qs.set('pill_size', String(params.pillSize));
    qs.set('pill_lh', String(params.pillLineHeight));
    qs.set('pill_pad', params.pillPad ? '1' : '0');
    qs.set('pill_grow_u', String(params.pillGrowU));
    if (params.delightSize) qs.set('delight_size', String(params.delightSize));
    const paramQs = qs.toString();

    const cards = filtered.map((r) => {
      const previewUrl = `/debug/face-test/preview?triplet=${encodeURIComponent(r.triplet.id)}&${paramQs}`;
      const flavor = r.triplet.flavor;
      const delightLabel = !r.delight
        ? `<span class="muted">delight: ${flavor === 'text-day' ? 'image (text-day, n/a)' : 'no body'}</span>`
        : r.delight.kind === 'bilingual'
          ? r.delight.overflow
            ? `<span class="bad">delight bilingual: +${r.delight.width - r.delight.budget}u over (ja=${r.delight.ja_max} en=${r.delight.en_max}; ${r.delight.width}/${r.delight.budget}u${r.delight.lineMismatch ? '; line-mismatch' : ''})</span>`
            : `<span class="ok">delight bilingual: ${r.delight.budget - r.delight.width}u to spare</span>`
          : r.delight.overflow
            ? `<span class="bad">delight mono: ${r.delight.visual_rows}/${r.delight.cap_rows} rows${r.delight.wrapped ? ' (wrap)' : ''} (lines=${r.delight.lines}, max=${r.delight.max_chars}, size=${r.delight.size}u)</span>`
            : `<span class="ok">delight mono: ${r.delight.visual_rows}/${r.delight.cap_rows} rows</span>`;
      const pillLabel = !r.pill
        ? `<span class="muted">pill: no body</span>`
        : r.pill.overflow
          ? `<span class="bad">pill: +${r.pill.chars - r.pill.capacity} chars over (${r.pill.chars}/${r.pill.capacity}; ${r.pill.charsPerLine}cpl × ${r.pill.rows}r)</span>`
          : `<span class="ok">pill: ${r.pill.capacity - r.pill.chars} chars to spare</span>`;
      return `
<section class="card">
  <header>
    <h2>${r.triplet.id}</h2>
    <div class="meta">
      <span>flavor: ${flavor}</span>
      <span>summary slot: <code>${r.triplet.summarySlot}</code></span>
      <span><a href="${previewUrl}" target="_blank">open</a></span>
    </div>
    <div class="meta">${delightLabel}</div>
    <div class="meta">${pillLabel}</div>
  </header>
  <iframe loading="lazy" src="${previewUrl}" width="1200" height="825"></iframe>
</section>`;
    }).join('\n');

    const summaryLine =
      `Sizes: delight=${params.delightSize ?? 'per-form'} · ja=${params.jaSize} · en=${params.enSize} · ` +
      `pill=${params.pillSize}u/lh=${params.pillLineHeight}/pad=${params.pillPad ? 1 : 0} · ` +
      `pill_grow=${params.pillGrowU}u (delight body=${BOTTOM_TOTAL_DEBUG_HINT(params.pillGrowU)}u, pill body=${439 + params.pillGrowU}u). ` +
      `Universe: ${universe} triplets; ${overflowing.length} overflow; showing ${filtered.length} ` +
      (showAll ? '(all=1).' : `(dominance frontier${margin > 0 ? ` ±${margin}` : ''}).`);

    const page = `<!doctype html>
<html><head><meta charset="utf-8">
<title>Summary face overflow grid</title>
<style>
  body { margin: 0; font-family: -apple-system, BlinkMacSystemFont, sans-serif; background: #f4f4f4; color: #222; }
  .summary { position: sticky; top: 0; background: #fff; border-bottom: 1px solid #ddd; padding: 12px 24px; z-index: 10; }
  .summary form { display: flex; flex-wrap: wrap; gap: 12px; align-items: center; margin-top: 8px; font-size: 13px; }
  .summary label { display: inline-flex; align-items: center; gap: 4px; }
  .summary input[type=number], .summary input[type=text] { width: 64px; }
  .card { margin: 24px auto; width: 1200px; background: #fff; box-shadow: 0 1px 3px rgba(0,0,0,.1); }
  .card header { padding: 12px 16px; border-bottom: 1px solid #eee; display: flex; flex-direction: column; gap: 4px; }
  .card h2 { margin: 0; font-size: 16px; font-family: ui-monospace, SFMono-Regular, monospace; word-break: break-all; }
  .card .meta { display: flex; gap: 16px; font-size: 12px; color: #666; flex-wrap: wrap; }
  .card .meta code { font-family: ui-monospace, SFMono-Regular, monospace; }
  .card .meta .bad { color: #b00; font-weight: 600; }
  .card .meta .ok { color: #060; }
  .card .meta .muted { color: #999; }
  .card iframe { display: block; border: 0; }
</style>
</head><body>
<div class="summary">
  <strong>Summary face overflow grid</strong>
  <span style="margin-left:12px;color:#666">${summaryLine}</span>
  <form method="get" action="/debug/face-test/all">
    <label>delight_size <input name="delight_size" type="text" value="${params.delightSize ?? ''}" placeholder="per-form"></label>
    <label>ja <input name="ja" type="number" value="${params.jaSize}" min="20" max="60"></label>
    <label>en <input name="en" type="number" value="${params.enSize}" min="20" max="60"></label>
    <label>pill_size <input name="pill_size" type="number" value="${params.pillSize}" min="16" max="48"></label>
    <label>pill_lh <input name="pill_lh" type="text" value="${params.pillLineHeight}"></label>
    <label>pill_pad <select name="pill_pad"><option value="1" ${params.pillPad ? 'selected' : ''}>1</option><option value="0" ${!params.pillPad ? 'selected' : ''}>0</option></select></label>
    <label>pill_grow_u <input name="pill_grow_u" type="number" value="${params.pillGrowU}" step="30"></label>
    <label>margin <input name="margin" type="number" value="${margin}" min="0"></label>
    <label><input name="all" type="checkbox" value="1" ${showAll ? 'checked' : ''}> show all</label>
    <button type="submit">apply</button>
  </form>
</div>
${cards || '<p style="padding:48px;text-align:center;color:#666">No overflow at current params — every triplet fits.</p>'}
</body></html>`;
    return new Response(page, { status: 200, headers: { 'content-type': 'text/html; charset=utf-8' } });
  } catch (err) {
    return mapError(err, c);
  }
});

// Helper just for the summary line above (avoids importing the constant
// twice while keeping the math close to the tooltip text).
function BOTTOM_TOTAL_DEBUG_HINT(growU: number): number {
  return 1076 - 439 - growU;
}

// --- Clock-zone metadata endpoint --------------------------------------------
//
// Returns the most recent (x, y, w, h, font_size) of the clock element from
// the named mode's last PNG render. The device firmware fetches this on every
// Full wake and caches the values in RTC RAM so the offline 1-bit partial
// path can place its baked Fraunces glyphs at exactly where the rendered face
// painted the clock — no matter which face/variant rendered last.
//
// 404 means either:
//   - The mode hasn't been rendered yet (cold renderer start), or
//   - The mode has no clock-shaped DOM element (e.g. Night, which splits hh/mm).
// In both cases the firmware falls back to Full at the cadence boundary.

app.get('/display/:mode/clock-zone.json', (c) => {
  const mode = c.req.param('mode');
  if (!isMode(mode)) return c.text(notFoundBody(mode), 404);
  const z = clockZoneByMode.get(mode);
  if (!z) return c.text('no clock zone for mode\n', 404);
  return c.json(z, 200);
});

// --- Eval pages: side-by-side variant comparison -----------------------------

app.get('/eval/:mode', (c) => {
  const mode = c.req.param('mode');
  if (!isMode(mode)) return c.text(notFoundBody(mode), 404);
  // Summary supports a/b/c. Other modes show a single column.
  const variants = mode === 'summary' ? ['a', 'b', 'c'] : [''];
  const cards = variants
    .map((v) => {
      const label = v ? `Variant ${v.toUpperCase()}` : 'Default';
      const qs = v ? `?variant=${v}` : '';
      // Cache-busting query param ensures each reload re-renders.
      const ts = Date.now();
      return `<figure class="card">
  <figcaption>
    <span class="title">${label}</span>
    <span class="links">
      <a href="/display/${mode}/preview${qs}" target="_blank">HTML</a> ·
      <a href="/display/${mode}.png${qs}" target="_blank">PNG</a>
    </span>
  </figcaption>
  <div class="frame"><img src="/display/${mode}.png${qs}${qs ? '&' : '?'}ts=${ts}" alt="${label}"></div>
</figure>`;
    })
    .join('');
  return new Response(
    `<!doctype html><html><head><meta charset="utf-8"><title>Eval — ${mode}</title>
<style>
  :root { color-scheme: light; }
  body { margin: 0; padding: 24px; font: 14px/1.4 -apple-system, system-ui, sans-serif; background: #f7f7f7; color: #222; }
  h1 { margin: 0 0 8px; font-weight: 500; }
  nav { margin-bottom: 24px; font-size: 13px; color: #666; }
  nav a { color: #06c; text-decoration: none; margin-right: 12px; }
  .grid {
    display: flex;
    gap: 18px;
    overflow-x: auto;
    padding-bottom: 12px;
    scroll-snap-type: x mandatory;
  }
  .card {
    background: #fff;
    border-radius: 6px;
    box-shadow: 0 1px 3px rgba(0,0,0,.08);
    padding: 12px;
    margin: 0;
    flex: 0 0 720px;
    scroll-snap-align: start;
  }
  figcaption { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 8px; }
  .title { font-weight: 600; font-size: 14px; }
  .links { font-size: 12px; color: #888; }
  .links a { color: #06c; text-decoration: none; }
  .frame { width: 100%; aspect-ratio: 1200 / 825; background: #ececec; border: 1px solid #ddd; overflow: hidden; }
  .frame img { width: 100%; height: 100%; object-fit: contain; image-rendering: pixelated; display: block; }
  .legend { font-size: 12px; color: #888; margin-top: 24px; padding-top: 12px; border-top: 1px solid #ddd; }
</style></head><body>
<h1>${mode} — variant comparison</h1>
<nav>
  <a href="/eval/summary">summary</a>
  <a href="/eval/weather">weather</a>
  <a href="/eval/gallery">gallery</a>
  <a href="/eval/night">night</a>
  <a href="/eval/now-playing">now-playing</a>
</nav>
<div class="grid">${cards}</div>
<p class="legend">Each card shows the final dithered PNG — the exact output the Inkplate displays. Click HTML to see the raw layout in a new tab, or PNG for the full-size image.</p>
</body></html>`,
    { status: 200, headers: { 'content-type': 'text/html; charset=utf-8' } },
  );
});

// --- Dither test harness page ------------------------------------------------

app.get('/dither-test', async (c) => {
  const { renderDitherTestPage } = await import('./tools/dither-test.js');
  return new Response(await renderDitherTestPage(), {
    status: 200,
    headers: { 'content-type': 'text/html; charset=utf-8' },
  });
});

// --- Input publisher endpoint ------------------------------------------------

app.post('/inputs/:name', async (c) => {
  const name = c.req.param('name');
  if (!INPUT_NAME_RE.test(name) || !WRITABLE_INPUTS.has(name)) {
    return c.text(`unknown input "${name}"\n`, 404);
  }

  const token = process.env.RENDERER_INPUT_TOKEN;
  const authz = c.req.header('authorization') ?? '';
  if (!authz) return c.text('missing Authorization header\n', 401);
  const m = /^Bearer\s+(\S+)$/.exec(authz);
  if (!m) return c.text('malformed Authorization header\n', 401);
  if (!token || m[1] !== token) return c.text('forbidden\n', 403);

  let raw: ArrayBuffer;
  try {
    raw = await c.req.arrayBuffer();
  } catch {
    return c.text('could not read body\n', 400);
  }
  if (raw.byteLength > MAX_INPUT_BYTES) {
    return c.text(`body exceeds ${MAX_INPUT_BYTES} bytes\n`, 413);
  }
  const text = Buffer.from(raw).toString('utf8');
  let parsed: Record<string, unknown>;
  try {
    parsed = JSON.parse(text) as Record<string, unknown>;
  } catch {
    return c.text('body is not valid JSON\n', 400);
  }

  // Sonos enrichment: when the publisher sends a `media_content_id`, run the
  // Spotify+MusicBrainz enrichment pipeline before persisting so that the
  // next render sees composer/work/movement/performers/year. Failures are
  // logged but not surfaced; the unenriched payload still produces a valid
  // (flat-layout) Now-Playing render.
  let bodyToWrite = text;
  if (name === 'sonos') {
    try {
      const enriched = await enrichFromSonos(parsed as { media_content_id?: string | null });
      if (enriched) {
        // Spread enrichment over the publisher's payload. The enrichment
        // module sets `art_url` only when it has a Spotify CDN URL; when
        // omitted the publisher's existing `art_url` (HA proxy URL) wins.
        const merged: Record<string, unknown> = { ...parsed, ...enriched };
        bodyToWrite = JSON.stringify(merged);
      }
    } catch (err) {
      log.warn({ err }, 'sonos enrichment failed; persisting unenriched payload');
    }
  }

  const dir = inputsDir();
  await fs.mkdir(dir, { recursive: true });
  const finalPath = path.join(dir, `${name}.json`);
  const tmpPath = path.join(dir, `.${name}.${randomUUID()}.tmp`);
  try {
    await fs.writeFile(tmpPath, bodyToWrite);
    await fs.rename(tmpPath, finalPath);
  } catch (err) {
    await fs.rm(tmpPath, { force: true }).catch(() => {});
    log.error({ err, name }, 'input publish failed');
    return c.text('write failed\n', 500);
  }
  return new Response(null, { status: 204 });
});

// --- Error mapping -----------------------------------------------------------

function notFoundBody(mode: string): string {
  return `unknown mode "${mode}". Valid: ${MODES.join(', ')}\n`;
}

function mapError(err: unknown, _c: unknown): Response {
  if (err instanceof MissingInputError) {
    return new Response(`required input missing: ${err.inputName}\n`, { status: 503 });
  }
  if (err instanceof VerseOverflowError) {
    return new Response(
      JSON.stringify({
        error: 'VERSE_OVERFLOW',
        zone: err.zoneId,
        inputLength: err.inputLength,
        budget: err.budget,
      }),
      { status: 422, headers: { 'content-type': 'application/json' } },
    );
  }
  if (err instanceof z.ZodError) {
    return new Response(
      JSON.stringify({ error: 'VALIDATION', issues: err.issues }),
      { status: 400, headers: { 'content-type': 'application/json' } },
    );
  }
  log.error({ err }, 'render failed');
  return new Response(`internal error: ${(err as Error).message}\n`, { status: 500 });
}

// --- Bootstrap ---------------------------------------------------------------

/**
 * Try to bind the listening socket, retrying with backoff on EADDRINUSE.
 *
 * Why this exists: when the process is restarted by launchd's KeepAlive,
 * the previous instance's socket is often still in TIME_WAIT. Without a
 * retry the new process dies with EADDRINUSE; launchd waits its
 * ThrottleInterval (10 s) and tries again — repeating until TIME_WAIT
 * clears (30-60 s on macOS), spamming the err log with hundreds of stack
 * traces. The retry inside the same process drains those waits cheaply.
 */
async function listenWithRetry(): Promise<ReturnType<typeof serve>> {
  const maxAttempts = 180;  // 3 min @ 1 s — covers macOS TIME_WAIT (typ. 30-60 s) plus margin.
  const backoffMs = 1000;
  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    try {
      return await new Promise<ReturnType<typeof serve>>((resolve, reject) => {
        const s = serve({ fetch: app.fetch, hostname: HOST, port: PORT }, (info) => {
          log.info(
            { port: info.port, host: HOST, templates: TEMPLATES_DIR, attempt },
            'renderer listening',
          );
          resolve(s);
        });
        // The serve() callback fires only on success; bind failures surface
        // as an 'error' event on the underlying http.Server.
        s.on('error', (err: Error) => reject(err));
      });
    } catch (err) {
      const code = (err as NodeJS.ErrnoException)?.code;
      if (code === 'EADDRINUSE' && attempt < maxAttempts) {
        // Stop logging every attempt — every 10th is enough to confirm progress
        // without filling the err log with hundreds of identical lines.
        if (attempt === 1 || attempt % 10 === 0) {
          log.warn({ attempt, port: PORT }, 'EADDRINUSE — retrying in 1 s');
        }
        await new Promise((r) => setTimeout(r, backoffMs));
        continue;
      }
      throw err;
    }
  }
  // Retry budget exhausted — likely a real conflict (another renderer running
  // standalone, or a different service grabbed the port). Exit so launchd
  // re-spawns us with a fresh ThrottleInterval instead of leaving an orphaned
  // process alive (which the uncaughtException/unhandledRejection handlers
  // would otherwise mask). Exit code 75 = EX_TEMPFAIL by sysexits convention.
  log.fatal(
    { port: PORT, attempts: maxAttempts },
    'EADDRINUSE persisted past retry budget — exiting for launchd to restart',
  );
  process.exit(75);
}

async function main(): Promise<void> {
  // Catch-all error handlers — without these, any stray unhandled rejection
  // (e.g. a Playwright timeout that escapes the request scope) takes down
  // the whole process, which then triggers a launchd relaunch and a fresh
  // EADDRINUSE crash-loop episode.
  process.on('uncaughtException', (err) => {
    log.error({ err }, 'uncaughtException — keeping process alive');
  });
  process.on('unhandledRejection', (reason) => {
    log.error({ reason }, 'unhandledRejection — keeping process alive');
  });

  // Warm the browser in the background so first request is fast.
  ensureBrowser().catch((err) => log.error({ err }, 'playwright launch failed'));

  const server = await listenWithRetry();

  const shutdown = async (signal: string): Promise<void> => {
    log.info({ signal }, 'shutting down');
    // Wait for the listening socket to fully close before exit. If we let
    // process.exit() run before close completes, the kernel keeps the
    // socket in TIME_WAIT and the next launchd-spawned instance hits
    // EADDRINUSE. A 5-s safety timeout covers the case where a hung
    // request-in-flight blocks close() from completing — better to drop
    // the connection than hang forever.
    await new Promise<void>((resolve) => {
      let settled = false;
      const finish = (): void => {
        if (!settled) {
          settled = true;
          resolve();
        }
      };
      server.close(() => finish());
      setTimeout(finish, 5000).unref();
    });
    await closeBrowser();
    process.exit(0);
  };
  process.on('SIGINT', () => void shutdown('SIGINT'));
  process.on('SIGTERM', () => void shutdown('SIGTERM'));
}

if (import.meta.url === `file://${process.argv[1]}`) {
  void main();
}

export { app };
