/**
 * Font file presence + Romanian diacritic coverage check.
 *
 * The full UCS subtable parse would require a TTF reader dependency. This
 * tool performs a pragmatic coverage test: if the font files exist AND the
 * check is run with Playwright available, render each Romanian diacritic
 * into an offscreen canvas and verify non-zero pixel coverage.
 *
 * For the initial apply we implement only the file-presence check; the
 * canvas-based coverage step is a follow-up (marked TODO below).
 */
import fs from 'node:fs/promises';
import path from 'node:path';
import { FONTS_DIR } from '../config.js';

const REQUIRED = [
  'Fraunces[opsz,wght].woff2',
  'Fraunces-Italic[opsz,wght].woff2',
  'IBMPlexMono-Regular.woff2',
  'IBMPlexSans-Light.woff2',
  'IBMPlexSans-Regular.woff2',
];

async function main(): Promise<void> {
  const issues: string[] = [];
  for (const name of REQUIRED) {
    const full = path.join(FONTS_DIR, name);
    try {
      await fs.access(full);
    } catch {
      issues.push(`missing: ${name}`);
    }
  }
  // TODO: render `ă â î ș ț` at 72px with Fraunces and assert non-empty raster.
  if (issues.length) {
    // In dev, this is a warning. Templates degrade to fallback families until fonts arrive.
    console.warn('[lint-fonts] missing font files (templates will fall back):');
    for (const i of issues) console.warn('  ' + i);
    return;
  }
  console.log(`[lint-fonts] ${REQUIRED.length} font files present`);
}

if (import.meta.url === `file://${process.argv[1]}`) {
  void main();
}
