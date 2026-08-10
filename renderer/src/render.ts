import sharp from 'sharp';
import { closeBrowser, ensureBrowser } from './browser.js';
import { VIEWPORT, ditherPlacement } from './config.js';
import { log } from './logger.js';
import { blueNoiseDither, quantizeToPalette, type DitherMask } from './image/dither.js';
import { assertPaletteOnly } from './image/palette.js';

// Errors thrown by Playwright when the cached Chromium has died between
// `ensureBrowser()` returning and the actual call. Catching these lets us
// trigger one relaunch+retry per request instead of 500'ing — without that,
// a Chromium crash leaves every subsequent render failing until the renderer
// process itself is restarted.
function isDeadContextError(err: unknown): boolean {
  const m = err instanceof Error ? err.message : String(err);
  return (
    m.includes('Target page, context or browser has been closed') ||
    m.includes('Browser has been closed') ||
    m.includes('Target closed')
  );
}

export interface RenderRequest {
  /** Fully-qualified URL to load (http://localhost:PORT/internal/template/... or file://...) */
  url: string;
  /**
   * Which pixels get error diffusion, from the mode's `ditherMask()`.
   *
   * Honoured when placement is `server`: masked pixels are blue-noise
   * dithered onto the Inkplate palette, unmasked pixels are hard-quantized to
   * the nearest palette value so text keeps clean edges.
   * `false` means the face has no photographic zone and quantizes throughout.
   *
   * Ignored under `'device'`, where the Inkplate library dithers on decode.
   */
  dither: boolean | DitherMask;
}

/**
 * Position and font size of the clock zone in the rendered face. Surfaced
 * to the device firmware via the `/display/:mode/clock-zone.json` endpoint
 * so the partial-update path can draw at the exact same coordinates the
 * full render painted, regardless of which mode/variant the renderer chose
 * (gallery has three layouts; weather/summary one each).
 */
export interface ClockZone {
  x: number;
  y: number;
  w: number;
  h: number;
  font_size: number;  // CSS px = panel u
}

export interface RenderResult {
  png: Buffer;
  clockZone: ClockZone | null;
}

/**
 * Load a template URL in the shared Playwright context, screenshot at 1200×825,
 * convert to single-channel 8-bit greyscale, and return a PNG.
 *
 * No supersample, no resample, no tonal manipulation — one screenshot, one
 * colourspace conversion. Under `RENDERER_DITHER=server` a palette-mapping
 * pass is added: Floyd-Steinberg inside the mode's photo mask, nearest-palette
 * outside it. Under `device` the bytes go out at full range and the Inkplate
 * library maps them, which is the historical path.
 *
 * Also extracts the clock zone from the rendered DOM (when present) so the
 * device firmware can place its 1-bit partial-update digits at the exact
 * pixel coordinates the full render painted.
 */
export async function renderToPng(req: RenderRequest & { url: string }): Promise<RenderResult> {
  try {
    return await renderOnce(req);
  } catch (err) {
    if (!isDeadContextError(err)) throw err;
    log.warn({ err: (err as Error).message }, 'dead chromium context — relaunching and retrying once');
    await closeBrowser();
    return renderOnce(req);
  }
}

async function renderOnce(_req: RenderRequest & { url: string }): Promise<RenderResult> {
  const ctx = await ensureBrowser();
  const page = await ctx.newPage();
  try {
    await page.goto(_req.url, { waitUntil: 'networkidle' });
    await page.evaluate(() => (document as Document).fonts.ready);

    // Selectors covering every face that has a clock-shaped zone:
    //   summary, weather, gallery-visual          → .clock
    //   gallery-visual (split layout)             → .gv-clock
    //   gallery-text                              → .gt-corner-time
    //   now-playing                               → .np-clock
    //   night                                     → .night-phrase
    // Night's `.night-phrase` carries the full fuzzy-time string (e.g.
    // "quarter past two"); the firmware blits a pre-baked 1-bit bitmap
    // for the phrase per add-night-text-clock-partials. We surface the
    // bounding rectangle here so the firmware knows where to paint.
    const clockZone = await page.evaluate(() => {
      const el = document.querySelector(
        '.clock, .gv-clock, .gt-corner-time, .np-clock, .night-phrase',
      ) as HTMLElement | null;
      if (!el) return null;
      const r = el.getBoundingClientRect();
      const cs = getComputedStyle(el);
      return {
        x: Math.round(r.x),
        y: Math.round(r.y),
        w: Math.round(r.width),
        h: Math.round(r.height),
        font_size: Math.round(parseFloat(cs.fontSize)),
      };
    });

    const screenshot = await page.screenshot({
      type: 'png',
      clip: { x: 0, y: 0, width: VIEWPORT.width, height: VIEWPORT.height },
      omitBackground: false,
    });
    // `.greyscale()` desaturates but leaves three identical channels;
    // `.toColourspace('b-w')` is what actually makes the PNG single-channel.
    // pngle decodes colour-type 0 by expanding v[1] = v[2] = v[0], so the
    // device sees identical pixel values either way — just fewer bytes.
    const grey = sharp(screenshot).greyscale().toColourspace('b-w');

    if (ditherPlacement() !== 'server') {
      const png = await grey.png({ compressionLevel: 9 }).toBuffer();
      return { png, clockZone };
    }

    const { data, info } = await grey.raw().toBuffer({ resolveWithObject: true });
    if (info.channels !== 1) {
      throw new Error(`render: expected 1-channel greyscale, got ${info.channels}`);
    }
    const src = new Uint8Array(data.buffer, data.byteOffset, data.length);
    const quantized =
      _req.dither === false
        ? quantizeToPalette(src)
        : blueNoiseDither(
            src,
            info.width,
            info.height,
            _req.dither === true ? undefined : _req.dither,
          );
    // The device maps palette values onto panel levels with a bare
    // `floor(v/32)`; an out-of-palette byte would land on the wrong level
    // silently, so fail the render instead of shipping it.
    assertPaletteOnly(quantized);
    const png = await sharp(quantized, {
      raw: { width: info.width, height: info.height, channels: 1 },
    })
      // Sharp promotes a 1-channel raw buffer back to sRGB on PNG encode
      // unless the output colourspace is pinned, which silently tripled the
      // payload the device downloads.
      .toColourspace('b-w')
      .png({ compressionLevel: 9 })
      .toBuffer();
    return { png, clockZone };
  } finally {
    await page.close();
  }
}
