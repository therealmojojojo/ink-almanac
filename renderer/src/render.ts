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
 * Load a template URL in the shared Playwright context, screenshot at 1200×825,
 * convert to single-channel 8-bit greyscale, and return a lossless PNG.
 * No supersample, no server-side quantize, no server-side dither. The device's
 * Inkplate library handles palette mapping — proven crisp on the panel (v.
 * MagInkDash, which follows the same one-pass flow).
 */
export async function renderToPng(_req: RenderRequest & { url: string }): Promise<Buffer> {
  const ctx = await ensureBrowser();
  const page = await ctx.newPage();
  try {
    await page.goto(_req.url, { waitUntil: 'networkidle' });
    await page.evaluate(() => (document as Document).fonts.ready);
    const screenshot = await page.screenshot({
      type: 'png',
      clip: { x: 0, y: 0, width: VIEWPORT.width, height: VIEWPORT.height },
      omitBackground: false,
    });
    return await sharp(screenshot)
      .greyscale()
      .png({ compressionLevel: 9 })
      .toBuffer();
  } finally {
    await page.close();
  }
}
