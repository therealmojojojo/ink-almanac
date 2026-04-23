/**
 * Template CSS lint: palette-only colors, allowed family list, size floor.
 */
import fs from 'node:fs/promises';
import path from 'node:path';
import { TEMPLATES_DIR } from '../config.js';

const ALLOWED_FAMILIES = new Set([
  "'Fraunces'",
  "'IBM Plex Mono'",
  "'IBM Plex Sans'",
  "'Times New Roman'",
  "'Menlo'",
  "'Helvetica Neue'",
  'serif',
  'monospace',
  'sans-serif',
]);

const ALLOWED_COLOR_TOKENS = new Set([
  'var(--ink)',
  'var(--paper)',
  'var(--mid)',
  'var(--faint)',
  'transparent',
  'inherit',
  'initial',
  'currentColor',
]);
const ALLOWED_HEX = new Set(['#000', '#ececec', '#3a3a3a', '#909090']);
const CHROME_SELECTORS = new Set<string>(); // size-floor exempt selectors

async function walk(dir: string, acc: string[]): Promise<string[]> {
  for (const e of await fs.readdir(dir, { withFileTypes: true })) {
    const full = path.join(dir, e.name);
    if (e.isDirectory()) await walk(full, acc);
    else if (e.name.endsWith('.css')) acc.push(full);
  }
  return acc;
}

function checkColors(css: string, file: string, issues: string[]): void {
  // Flag hex colors not in allow-list
  const hexRe = /#(?:[0-9a-fA-F]{3,8})/g;
  for (const m of css.matchAll(hexRe)) {
    if (!ALLOWED_HEX.has(m[0].toLowerCase())) {
      issues.push(`${file}: non-palette hex "${m[0]}"`);
    }
  }
  // Flag rgb()/rgba()/hsl()
  if (/\b(?:rgb|rgba|hsl|hsla)\s*\(/.test(css)) {
    issues.push(`${file}: rgb/hsl color function (use palette vars)`);
  }
}

function checkFamilies(css: string, file: string, issues: string[]): void {
  const fontFamilyRe = /font-family\s*:\s*([^;]+);/gi;
  for (const m of css.matchAll(fontFamilyRe)) {
    const families = m[1]!.split(',').map((s) => s.trim());
    for (const fam of families) {
      // Accept `var(--font-*)` forms as well
      if (fam.startsWith('var(')) continue;
      if (!ALLOWED_FAMILIES.has(fam)) {
        issues.push(`${file}: disallowed font-family "${fam}"`);
      }
    }
  }
}

function checkSizeFloor(css: string, file: string, issues: string[]): void {
  // Typography-routing size floor: ≥25u, except chrome "explicitly marked
  // in templates." Convention here: a rule is chrome when either
  //   (a) it carries a trailing `/* chrome */` comment on the font-size, or
  //   (b) it sets `text-transform: uppercase` with `letter-spacing:` set
  //       (i.e., it's a mono-caps status label — the canonical chrome
  //       pattern used by battery indicator, source/astro/HN labels, etc.)
  const ruleRe = /([.#\w\s\->,:()[\]]+)\{([^}]*)\}/gs;
  for (const m of css.matchAll(ruleRe)) {
    const selector = m[1]!.trim();
    const block = m[2]!;
    const sizeMatch = /font-size\s*:\s*calc\(\s*(\d+)\s*\*\s*var\(--u\)\)([^;]*)/.exec(block);
    if (!sizeMatch) continue;
    const n = Number(sizeMatch[1]);
    if (n >= 25) continue;
    const trailing = sizeMatch[2] ?? '';
    const hasChromeMarker = /\/\*\s*chrome\s*\*\//.test(trailing);
    const hasUpperLS =
      /text-transform\s*:\s*uppercase/.test(block) &&
      /letter-spacing\s*:/.test(block);
    if (hasChromeMarker || hasUpperLS) continue;
    if (CHROME_SELECTORS.has(selector)) continue;
    issues.push(
      `${file}: font-size ${n}u below 25u floor for "${selector}" (add \`/* chrome */\` or use mono-caps chrome pattern)`,
    );
  }
}

async function main(): Promise<void> {
  const files = await walk(TEMPLATES_DIR, []);
  const issues: string[] = [];
  for (const f of files) {
    const css = await fs.readFile(f, 'utf8');
    checkColors(css, f, issues);
    checkFamilies(css, f, issues);
    checkSizeFloor(css, f, issues);
  }
  if (issues.length) {
    console.error('[lint-templates] issues:\n  ' + issues.join('\n  '));
    process.exit(1);
  }
  console.log(`[lint-templates] ${files.length} stylesheets clean`);
}

if (import.meta.url === `file://${process.argv[1]}`) {
  void main();
}
