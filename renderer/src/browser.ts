import { chromium, type Browser, type BrowserContext } from 'playwright';
import { VIEWPORT, DEVICE_SCALE_FACTOR } from './config.js';
import { log } from './logger.js';

let browser: Browser | undefined;
let context: BrowserContext | undefined;
let ready = false;

export async function ensureBrowser(): Promise<BrowserContext> {
  if (context) return context;
  log.info('launching chromium');
  browser = await chromium.launch({
    args: ['--disable-dev-shm-usage', '--no-sandbox', '--font-render-hinting=none'],
  });
  context = await browser.newContext({
    viewport: VIEWPORT,
    deviceScaleFactor: DEVICE_SCALE_FACTOR,
    reducedMotion: 'reduce',
    colorScheme: 'light',
  });
  ready = true;
  return context;
}

export function isBrowserReady(): boolean {
  return ready;
}

export async function closeBrowser(): Promise<void> {
  await context?.close().catch(() => {});
  await browser?.close().catch(() => {});
  browser = undefined;
  context = undefined;
  ready = false;
}
