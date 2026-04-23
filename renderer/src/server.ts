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
import { renderToPng } from './render.js';
import { VerseOverflowError } from './zoneApply.js';

/** Input names that `POST /inputs/:name` will accept. Matches the canonical
 *  set every face mode can consume; rejects everything else with 404 so the
 *  endpoint isn't a generic file-drop. */
const WRITABLE_INPUTS = new Set([
  'clock',
  'weather',
  'hn',
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
// The entity_picture URL already carries its own `token=...` query param, so
// this proxy forwards anonymously. We only allow the media_player_proxy path
// to avoid turning this into a general HA bypass.
app.get('/ha-proxy/api/media_player_proxy/:rest{.+}', async (c) => {
  // Resolve HA base URL from ha/secrets.yaml (same source as sim.ts).
  const haSecrets = path.resolve(ROOT, '..', 'ha', 'secrets.yaml');
  let haBase = '';
  try {
    const content = await fs.readFile(haSecrets, 'utf-8');
    const m = content.match(/^ha_base_url:\s*"?([^"\n]+?)"?\s*$/m);
    if (m?.[1]) haBase = m[1].trim();
  } catch {
    // fall through; empty haBase yields 502 below
  }
  if (!haBase) return c.text('ha_base_url not configured\n', 502);

  // Reconstruct the full target URL. We preserve any query params (token).
  const rest = c.req.param('rest');
  const url = new URL(c.req.url);
  const target = `${haBase.replace(/\/+$/, '')}/api/media_player_proxy/${rest}${url.search}`;

  // Shell out to curl — Node's fetch can't reach HA on this host.
  const { spawn } = await import('node:child_process');
  return new Promise<Response>((resolve) => {
    const child = spawn('curl', [
      '-s', '--max-time', '10',
      '-o', '-',
      '-D', '-', // headers to stdout, separated from body by blank line
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
      const png = await renderToPng({ url, dither: prepared.dither });
      return new Response(png as unknown as BodyInit, {
        status: 200,
        headers: {
          'content-type': 'image/png',
          'content-length': String(png.length),
          'cache-control': 'no-store',
          'x-render-mode': mode,
        },
      });
    } finally {
      htmlByToken.delete(token);
    }
  } catch (err) {
    return mapError(err, c);
  }
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
  try {
    JSON.parse(text);
  } catch {
    return c.text('body is not valid JSON\n', 400);
  }

  const dir = inputsDir();
  await fs.mkdir(dir, { recursive: true });
  const finalPath = path.join(dir, `${name}.json`);
  const tmpPath = path.join(dir, `.${name}.${randomUUID()}.tmp`);
  try {
    await fs.writeFile(tmpPath, text);
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

async function main(): Promise<void> {
  // Warm the browser in the background so first request is fast.
  ensureBrowser().catch((err) => log.error({ err }, 'playwright launch failed'));

  const server = serve({ fetch: app.fetch, hostname: HOST, port: PORT }, (info) => {
    log.info(
      { port: info.port, host: HOST, templates: TEMPLATES_DIR },
      'renderer listening',
    );
  });

  const shutdown = async (signal: string): Promise<void> => {
    log.info({ signal }, 'shutting down');
    server.close();
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
