/**
 * Build-time guard: each mode's `ditherMask()` rectangle must match the photo
 * element's actual laid-out geometry.
 *
 * The masks were authored while the server-side dither path was dead code
 * (`render.ts` accepted the `dither` parameter and discarded it), so their
 * hardcoded coordinates were never checked against a rendered face. Layouts
 * have moved since — `gallery-visual.css` still documents a 72 px caption band
 * while the grid actually reserves 108 px.
 *
 * A mask that is too small leaves photo edges hard-quantized (a visible band
 * at the boundary); too large and error diffusion speckles adjacent text.
 *
 * Run: npm run check-dither-masks
 * Writes an overlay PNG per mode to `test/dither/masks/<mode>.png` for eyeball
 * confirmation, and exits non-zero if any mask drifts past TOLERANCE_PX.
 */
import fs from 'node:fs/promises';
import path from 'node:path';
import { serve } from '@hono/node-server';
import sharp from 'sharp';
import { app } from '../server.js';
import { ensureBrowser, closeBrowser } from '../browser.js';
import { prepareMode } from '../modes/index.js';
import { ROOT, MODES, inputsDir, type Mode } from '../config.js';
import type { DitherMask } from '../image/dither.js';

/**
 * Photo element and its containing cell, per mode. `null` = no photo zone.
 *
 * Two rectangles matter, and they fail differently:
 *  - `img` — the painted pixels. Any painted pixel left OUTSIDE the mask
 *    hard-quantizes while its neighbours dither, which bands at the seam.
 *  - `cell` — the photo's own container. Mask pixels outside the cell land on
 *    text or rules and speckle them.
 *
 * Between the two (letterbox paper inside the cell, under `object-fit:
 * contain`) overshoot is harmless: it is a flat paper field a few pixels wide,
 * at the edge of a photo. Some of it is unavoidable — Now-Playing's album art
 * arrives as a URL, so its aspect ratio is unknown when the mask is built.
 */
const PHOTO_SELECTOR: Record<Mode, { img: string; cell: string } | null> = {
  summary: { img: '.summary-delight.image .body img', cell: '.summary-delight.image .body' },
  weather: null,
  gallery: { img: '.gv-image img', cell: '.gv-image' },
  night: { img: '.night-nocturne img', cell: '.night-nocturne' },
  'now-playing': { img: '.np-art img', cell: '.np-art' },
};

/** Slack on each edge before a coverage or overreach gap is called a failure. */
const TOLERANCE_PX = 2;

interface Rect {
  x: number;
  y: number;
  w: number;
  h: number;
}

/** Tight bounding box of the set pixels in a mask, or null if empty. */
function maskBBox(mask: DitherMask): Rect | null {
  let minX = mask.width;
  let minY = mask.height;
  let maxX = -1;
  let maxY = -1;
  for (let y = 0; y < mask.height; y++) {
    for (let x = 0; x < mask.width; x++) {
      if (mask.data[y * mask.width + x] === 0) continue;
      if (x < minX) minX = x;
      if (x > maxX) maxX = x;
      if (y < minY) minY = y;
      if (y > maxY) maxY = y;
    }
  }
  if (maxX < 0) return null;
  return { x: minX, y: minY, w: maxX - minX + 1, h: maxY - minY + 1 };
}

/**
 * The painted pixels, which is what the mask must track — not the element box.
 *
 * Under `object-fit: contain` the image is letterboxed inside its box, so the
 * painted rect is smaller than the element. Under `cover` (Night, Now-Playing)
 * the image is cropped to fill, so painted == element box. Getting this wrong
 * is how a mask ends up covering paper instead of photo.
 */
function paintedRect(box: Rect, naturalW: number, naturalH: number, objectFit: string): Rect {
  if (objectFit !== 'contain' || !naturalW || !naturalH) return box;
  const s = Math.min(box.w / naturalW, box.h / naturalH);
  const w = Math.round(naturalW * s);
  const h = Math.round(naturalH * s);
  return {
    x: Math.round(box.x + (box.w - w) / 2),
    y: Math.round(box.y + (box.h - h) / 2),
    w,
    h,
  };
}

function describe(r: Rect | null): string {
  return r ? `x ${r.x}–${r.x + r.w} y ${r.y}–${r.y + r.h} (${r.w}×${r.h})` : '(empty)';
}

/** Green tint where the mask is set, so drift is obvious against the face. */
async function writeOverlay(
  scenario: string,
  mode: Mode,
  png: Buffer,
  mask: DitherMask,
): Promise<string> {
  const { data, info } = await sharp(png).ensureAlpha().raw().toBuffer({ resolveWithObject: true });
  const out = Buffer.from(data);
  for (let i = 0, p = 0; i < mask.data.length; i++, p += info.channels) {
    if (mask.data[i] === 0) continue;
    out[p] = Math.round(out[p]! * 0.55);
    out[p + 2] = Math.round(out[p + 2]! * 0.55);
  }
  const dir = path.join(ROOT, 'test/dither/masks');
  await fs.mkdir(dir, { recursive: true });
  const file = path.join(dir, `${scenario}-${mode}.png`);
  await sharp(out, { raw: { width: info.width, height: info.height, channels: info.channels } })
    .png()
    .toFile(file);
  return path.relative(ROOT, file);
}

/**
 * Fixture scenarios covering the layout branches a single day's rotation can't
 * reach — split vs the three landscape gallery variants, a visual Summary
 * companion, Now-Playing with art, Night with a nocturne. Without these the
 * check only ever exercises whatever happens to be published today.
 */
const SCENARIO_DIR = path.join(ROOT, 'test/fixtures/dither-masks');

async function scenarios(): Promise<Array<{ name: string; dir: string }>> {
  if (process.env.CHECK_MASKS_LIVE === '1') {
    return [{ name: 'live', dir: inputsDir() }];
  }
  const entries = await fs.readdir(SCENARIO_DIR, { withFileTypes: true });
  return entries
    .filter((e) => e.isDirectory())
    .map((e) => ({ name: e.name, dir: path.join(SCENARIO_DIR, e.name) }));
}

async function main(): Promise<void> {
  const port = Number(process.env.CHECK_MASKS_PORT ?? 8686);
  const server = serve({ fetch: app.fetch, port, hostname: '127.0.0.1' });
  const issues: string[] = [];
  const originalInputs = process.env.RENDERER_INPUTS_DIR;

  try {
    const ctx = await ensureBrowser();
    for (const scenario of await scenarios()) {
      process.env.RENDERER_INPUTS_DIR = scenario.dir;
      console.log(`\n[check-dither-masks] scenario: ${scenario.name}`);
      await checkScenario(ctx, port, scenario.name, issues);
    }
  } finally {
    if (originalInputs === undefined) delete process.env.RENDERER_INPUTS_DIR;
    else process.env.RENDERER_INPUTS_DIR = originalInputs;
    server.close();
    await closeBrowser();
  }

  if (issues.length > 0) {
    console.error(`\n[check-dither-masks] ${issues.length} issue(s):`);
    for (const i of issues) console.error(`  - ${i}`);
    process.exit(1);
  }
  console.log('\n[check-dither-masks] all masks match their laid-out photo geometry');
}

async function checkScenario(
  ctx: Awaited<ReturnType<typeof ensureBrowser>>,
  port: number,
  scenarioName: string,
  issues: string[],
): Promise<void> {
  for (const mode of MODES) {
    let prepared;
    try {
      prepared = await prepareMode(mode);
    } catch (err) {
      console.log(
        `[check-dither-masks]   ${mode}: SKIP — inputs unavailable (${(err as Error).message})`,
      );
      continue;
    }

    const selector = PHOTO_SELECTOR[mode];
    const mask = prepared.dither;

    // `/display/:mode/preview` serves the same HTML `prepareMode` just
    // produced, over HTTP, so relative /static and /inputs URLs resolve
    // exactly as they do in a real render.
    const page = await ctx.newPage();
    let photo: Rect | null = null;
    let cell: Rect | null = null;
    let png: Buffer | undefined;
    try {
      await page.goto(`http://127.0.0.1:${port}/display/${mode}/preview`, {
        waitUntil: 'networkidle',
      });
      await page.evaluate(() => (document as Document).fonts.ready);
      if (selector) {
        const measured = await page.evaluate((sel) => {
          const el = document.querySelector(sel.img) as HTMLImageElement | null;
          const box = document.querySelector(sel.cell) as HTMLElement | null;
          if (!el || !box) return null;
          const r = el.getBoundingClientRect();
          const b = box.getBoundingClientRect();
          return {
            img: { x: r.x, y: r.y, w: r.width, h: r.height },
            cell: { x: b.x, y: b.y, w: b.width, h: b.height },
            nw: el.naturalWidth,
            nh: el.naturalHeight,
            fit: getComputedStyle(el).objectFit,
          };
        }, selector);
        if (measured) {
          photo = paintedRect(measured.img, measured.nw, measured.nh, measured.fit);
          cell = {
            x: Math.round(measured.cell.x),
            y: Math.round(measured.cell.y),
            w: Math.round(measured.cell.w),
            h: Math.round(measured.cell.h),
          };
        }
      }
      png = await page.screenshot({ type: 'png' });
    } finally {
      await page.close();
    }

    const hasMask = mask !== false && mask !== true;
    const bbox = hasMask ? maskBBox(mask as DitherMask) : null;

    if (mask === true) {
      issues.push(
        `${scenarioName}/${mode}: ditherMask() returns \`true\` (whole face). Text zones would be ` +
          `error-diffused; the mask must be scoped to the photo region.`,
      );
      continue;
    }

    if (!selector) {
      if (mask !== false) {
        issues.push(
          `${scenarioName}/${mode}: has no photo element but ditherMask() returned a mask`,
        );
      } else {
        console.log(`[check-dither-masks]   ${mode}: OK — no photo zone, mask disabled`);
      }
      continue;
    }

    if (!photo) {
      if (mask === false) {
        console.log(`[check-dither-masks]   ${mode}: OK — no photo present, mask disabled`);
      } else {
        issues.push(`${scenarioName}/${mode}: mask present but no element matched \`${selector}\``);
      }
      continue;
    }

    if (mask === false) {
      issues.push(
        `${scenarioName}/${mode}: photo present at ${describe(photo)} but ditherMask() returned false`,
      );
      continue;
    }

    const overlay = png
      ? await writeOverlay(scenarioName, mode, png, mask as DitherMask)
      : '(no overlay)';
    if (!bbox) {
      issues.push(
        `${scenarioName}/${mode}: ditherMask() returned a mask with no set pixels  → ${overlay}`,
      );
      continue;
    }

    // Coverage: every painted photo pixel must be inside the mask.
    const uncovered = Math.max(
      photo.x - bbox.x >= 0 ? 0 : bbox.x - photo.x,
      photo.y - bbox.y >= 0 ? 0 : bbox.y - photo.y,
      photo.x + photo.w - (bbox.x + bbox.w),
      photo.y + photo.h - (bbox.y + bbox.h),
    );

    // Overreach: no mask pixel may fall outside the photo's own cell.
    const escape = cell
      ? Math.max(
          cell.x - bbox.x,
          cell.y - bbox.y,
          bbox.x + bbox.w - (cell.x + cell.w),
          bbox.y + bbox.h - (cell.y + cell.h),
        )
      : 0;

    const line = `${scenarioName}/${mode}: mask ${describe(bbox)} / photo ${describe(photo)} / cell ${describe(cell)}`;
    if (uncovered > TOLERANCE_PX) {
      issues.push(
        `${line} — leaves ${uncovered}px of painted photo unmasked ` +
          `(bands at the seam)  → ${overlay}`,
      );
    } else if (escape > TOLERANCE_PX) {
      issues.push(
        `${line} — mask escapes the photo cell by ${escape}px ` +
          `(speckles adjacent text)  → ${overlay}`,
      );
    } else {
      const slack = cell ? Math.max(0, -escape) : 0;
      console.log(
        `[check-dither-masks]   ${mode}: OK — ${line}` +
          (slack > 0 ? ` (${slack}px letterbox slack inside cell)` : '') +
          `  → ${overlay}`,
      );
    }
  }
}

main().catch((err) => {
  console.error('[check-dither-masks] failed:', err);
  process.exit(1);
});
