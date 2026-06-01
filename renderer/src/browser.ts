import { chromium, type Browser, type BrowserContext } from 'playwright';
import { VIEWPORT, DEVICE_SCALE_FACTOR } from './config.js';
import { log } from './logger.js';

// Single shared Chromium + context for the lifetime of the renderer process.
// If the underlying Chromium dies (OOM, OS reaper, crash inside a page),
// the next `ensureBrowser()` relaunches. A stuck cached reference to a dead
// context is exactly what caused the 3-day "Target page, context or browser
// has been closed" outage we recovered from on 2026-06-01: every PNG request
// 500'd because `ensureBrowser()` kept handing out the same dead handle.

let browser: Browser | undefined;
let context: BrowserContext | undefined;

function aliveBrowser(): Browser | undefined {
  return browser && browser.isConnected() ? browser : undefined;
}

async function launch(): Promise<BrowserContext> {
  log.info('launching chromium');
  const b = await chromium.launch({
    args: ['--disable-dev-shm-usage', '--no-sandbox', '--font-render-hinting=none'],
  });
  // Drop cached refs the moment Chromium exits so the next ensureBrowser()
  // takes the launch path instead of handing back a dead context.
  b.on('disconnected', () => {
    log.warn('chromium disconnected; will relaunch on next request');
    if (browser === b) {
      browser = undefined;
      context = undefined;
    }
  });
  const ctx = await b.newContext({
    viewport: VIEWPORT,
    deviceScaleFactor: DEVICE_SCALE_FACTOR,
    reducedMotion: 'reduce',
    colorScheme: 'light',
  });
  browser = b;
  context = ctx;
  return ctx;
}

export async function ensureBrowser(): Promise<BrowserContext> {
  if (aliveBrowser() && context) return context;
  // Stale ref from a previous launch — clear before relaunching.
  if (browser) {
    log.warn('chromium context is dead; relaunching');
    await closeBrowser();
  }
  return launch();
}

export function isBrowserReady(): boolean {
  return aliveBrowser() !== undefined && context !== undefined;
}

export async function closeBrowser(): Promise<void> {
  await context?.close().catch(() => {});
  await browser?.close().catch(() => {});
  browser = undefined;
  context = undefined;
}
