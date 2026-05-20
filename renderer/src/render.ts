import sharp from 'sharp';
import { ensureBrowser } from './browser.js';
import { VIEWPORT } from './config.js';
import type { DitherMask } from './image/dither.js';

export interface RenderRequest {
  /** Fully-qualified URL to load (http://localhost:PORT/internal/template/... or file://...) */
  url: string;
  /** Retained for API compatibility; currently ignored. The device's Inkplate
   *  library dithers the 8-bit greyscale PNG we emit here onto the 3-bit panel
   *  palette, so a second server-side Floyd-Steinberg pass would just add
   *  noise. Reconsider if we ever drive a non-Inkplate target. */
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
 * convert to single-channel 8-bit greyscale, and return a lossless PNG.
 * No supersample, no server-side quantize, no server-side dither. The device's
 * Inkplate library handles palette mapping — proven crisp on the panel (v.
 * MagInkDash, which follows the same one-pass flow).
 *
 * Also extracts the clock zone from the rendered DOM (when present) so the
 * device firmware can place its 1-bit partial-update digits at the exact
 * pixel coordinates the full render painted.
 */
export async function renderToPng(_req: RenderRequest & { url: string }): Promise<RenderResult> {
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
    const png = await sharp(screenshot)
      .greyscale()
      .png({ compressionLevel: 9 })
      .toBuffer();
    return { png, clockZone };
  } finally {
    await page.close();
  }
}
