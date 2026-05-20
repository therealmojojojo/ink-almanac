/**
 * Bake the 25 fuzzy-time phrases the Night face uses on partial-cadence
 * wakes (every :15 / :30 / :45 from 22:00 to 06:30) into a C++ header for
 * on-device 1-bit partial refresh.
 *
 * Why we bake whole phrase bitmaps (vs the per-glyph approach in
 * bake-clock-glyphs.ts): the Night phrase is a 96u italic Fraunces string
 * with kerning, ligatures, and natural proportional spacing. Composing it
 * from per-glyph atoms at firmware-time would either drop the kerning
 * (visible at this size) or require shipping a layout engine. The
 * vocabulary is closed (25 deterministic phrases), so baking each as a
 * single 1-bit bitmap is the durable choice — ~6 KB per phrase ≈ 150 KB
 * of flash total, sitting in .rodata and survivable across deep sleep
 * (no PSRAM, no NVS partition needed).
 *
 * The phrase strings come from `renderer/src/modes/night.ts::nightPhrase`.
 * We DO NOT hardcode the phrase list here — that would let the renderer's
 * PNG render and the firmware's partial bitmap drift apart silently. The
 * bake script iterates every partial-eligible (h, m) in the Night tier
 * (22:00 → 06:30, m ∈ {15, 30, 45}; plus 06:15 only) and asks nightPhrase
 * for the canonical text. If nightPhrase ever changes vocabulary (e.g.
 * "twelve" → "midnight"), re-running the bake re-syncs both halves.
 *
 * Outputs:
 *   firmware/src/generated/night_phrases.h
 *   firmware/src/generated/night_phrases.cpp
 *
 * Run: `npm run bake:night-phrases` (in renderer/).
 *
 * Smoke check: `npm run bake:night-phrases -- --smoke` writes a 5×5
 * contact-sheet PNG to /tmp/night_phrases_preview.png so the operator can
 * eyeball the rendering before committing to a flash. The smoke artifact
 * does not include the C++ emit step.
 */

import { chromium, type Browser } from 'playwright';
import sharp from 'sharp';
import fs from 'node:fs/promises';
import path from 'node:path';
import { ROOT } from '../config.js';
import { nightPhrase } from '../modes/night.js';

const FIRMWARE_ROOT = path.resolve(ROOT, '..', 'firmware');
const HEADER_PATH = path.join(FIRMWARE_ROOT, 'src/generated/night_phrases.h');
const SOURCE_PATH = path.join(FIRMWARE_ROOT, 'src/generated/night_phrases.cpp');
const FONT_PATH = path.join(ROOT, 'templates/fonts/Fraunces[opsz,wght].woff2');

/**
 * The Night tier owns 22:00 → 06:30 local. Partial wakes fire at every
 * minute multiple of 15 (per `ha/config/wake_schedule.yaml`: night
 * `partial_min: 15`). Within that intersection, the operator's :00
 * is a Full (60-min full_min), and :15 / :30 / :45 are the eligible
 * partial minutes. 06:30 falls on the boundary where the Morning tier
 * takes over, so we include up to 06:15 (the last partial Night owns).
 *
 * The set:
 *   22:15, 22:30, 22:45
 *   23:15, 23:30, 23:45
 *   00:15, 00:30, 00:45
 *   01:15, 01:30, 01:45
 *   02:15, 02:30, 02:45
 *   03:15, 03:30, 03:45
 *   04:15, 04:30, 04:45
 *   05:15, 05:30, 05:45
 *   06:15                      = 25 phrases
 */
function eligibleMinutes(): Array<{ h: number; m: number; minOfDay: number }> {
  const out: Array<{ h: number; m: number; minOfDay: number }> = [];
  for (let minOfDay = 0; minOfDay < 24 * 60; minOfDay++) {
    if (minOfDay % 15 !== 0) continue;
    if (minOfDay % 60 === 0) continue;       // :00 is a Full, not a partial
    const h = Math.floor(minOfDay / 60);
    const m = minOfDay % 60;
    const inNightTier = h >= 22 || h < 6 || (h === 6 && m < 30);
    if (!inNightTier) continue;
    out.push({ h, m, minOfDay });
  }
  return out;
}

// Pixels with luminance > threshold → white, else black. Matches the night
// face's near-binary rendering of black ink on white (or near-white) page.
// 240 is the same threshold the clock-glyphs baker uses; the panel's
// dither library re-quantizes anyway.
const INK_THRESHOLD = 240;

interface BakedPhrase {
  minOfDay: number;
  text: string;
  width: number;             // tight-bbox crop, px
  height: number;            // ditto
  bitmap: Buffer;            // 1bpp, MSB-first, row-padded to byte boundary
}

/** Render one phrase, threshold to 1-bit, tight-crop. */
async function bakePhrase(
  browser: Browser,
  minOfDay: number,
  text: string,
  fontUrl: string,
): Promise<BakedPhrase> {
  // Stylesheet mirrors `.night-phrase` from renderer/templates/night/night.css
  // EXCEPT we render the phrase as an inline-block span (no flex/centering)
  // so the screenshot bounds tight to the ink. The firmware does the
  // vertical-centering math at blit time using the cached clock-zone height.
  const stylesheet = `
    @font-face {
      font-family: 'Fraunces';
      src: url('${fontUrl}') format('woff2-variations');
      font-weight: 100 900;
      font-style: italic;
      font-display: block;
    }
    html, body {
      margin: 0; padding: 0; background: white;
      -webkit-font-smoothing: antialiased;
      text-rendering: geometricPrecision;
    }
    #wrap {
      display: inline-block;
      padding: 96px;     /* generous slack so descenders/ascenders aren't clipped */
      background: white;
    }
    #zone {
      display: inline-block;
      font-family: 'Fraunces';
      font-variation-settings: 'opsz' 144, 'wght' 400;
      font-style: italic;
      font-size: 96px;
      line-height: 1.05;
      color: black;
      white-space: nowrap;
    }
  `;
  const html = `<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>${stylesheet}</style></head>
<body><div id="wrap"><span id="zone">${escapeHtml(text)}</span></div></body></html>`;

  const page = await browser.newPage({ deviceScaleFactor: 1 });
  await page.setContent(html);
  await page.evaluate(() => document.fonts.ready);
  const png = await page.screenshot({ omitBackground: false, fullPage: true });
  await page.close();

  const raw = await sharp(png).grayscale().raw().toBuffer({ resolveWithObject: true });
  const W = raw.info.width;
  const H = raw.info.height;
  const data = raw.data;

  // Tight-bbox crop: walk the whole frame, find the min/max coords of any
  // pixel darker than the ink threshold.
  let minX = W, maxX = -1, minY = H, maxY = -1;
  for (let y = 0; y < H; y++) {
    for (let x = 0; x < W; x++) {
      if (data[y * W + x]! < INK_THRESHOLD) {
        if (x < minX) minX = x;
        if (x > maxX) maxX = x;
        if (y < minY) minY = y;
        if (y > maxY) maxY = y;
      }
    }
  }
  if (maxX < 0 || maxY < 0) {
    throw new Error(`bake: no ink pixels found for minOfDay=${minOfDay} text="${text}"`);
  }

  const cropW = maxX - minX + 1;
  const cropH = maxY - minY + 1;
  const rowBytes = Math.ceil(cropW / 8);
  const bitmap = Buffer.alloc(rowBytes * cropH);
  for (let y = 0; y < cropH; y++) {
    for (let x = 0; x < cropW; x++) {
      const v = data[(minY + y) * W + (minX + x)]!;
      if (v < INK_THRESHOLD) {
        // MSB-first: bit 7 is leftmost, bit 0 is rightmost (within a byte).
        bitmap[y * rowBytes + (x >> 3)]! |= 1 << (7 - (x & 7));
      }
    }
  }

  return { minOfDay, text, width: cropW, height: cropH, bitmap };
}

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function emitHeader(): string {
  return `// firmware/src/generated/night_phrases.h
// AUTO-GENERATED by renderer/src/tools/bake-night-phrases.ts. Do not edit.
//
// Per add-night-text-clock-partials. The Night face's partial-cadence wakes
// (every :15 / :30 / :45 in the Night tier) blit one of these 1-bit phrase
// bitmaps onto the panel. The firmware looks up the right bitmap via
// phraseForMinute(min_of_day); a return value of nullptr means the wake
// minute is not in the partial-eligible set and the caller decides what
// to do (typically: return false from doPartial → promote to Full or skip).

#pragma once
#include <cstdint>

namespace fw::night_phrases {

struct Bitmap {
  uint16_t width;          // px (= panel u)
  uint16_t height;         // px
  const uint8_t* data;     // 1bpp, MSB-first within byte, row-major, padded
                           // to byte boundary; height * ceil(width / 8) bytes
};

// Returns nullptr if \`min_of_day\` is outside the 25-phrase set.
const Bitmap* phraseForMinute(int min_of_day);

}  // namespace fw::night_phrases
`;
}

function emitSource(phrases: BakedPhrase[]): string {
  const lines: string[] = [];
  lines.push('// firmware/src/generated/night_phrases.cpp');
  lines.push('// AUTO-GENERATED by renderer/src/tools/bake-night-phrases.ts. Do not edit.');
  lines.push('');
  lines.push('#include "night_phrases.h"');
  lines.push('');
  lines.push('namespace fw::night_phrases {');
  lines.push('');

  // One data array per phrase. Each is `static constexpr` so it lives in
  // .rodata (flash on the device, not RAM).
  for (let i = 0; i < phrases.length; i++) {
    const p = phrases[i]!;
    const label = `min ${p.minOfDay} — "${p.text}"`;
    lines.push(`// ${label}  (${p.width}×${p.height}, ${p.bitmap.length} bytes)`);
    lines.push(`static constexpr uint8_t kData_${p.minOfDay}[] = {`);
    const hex = Array.from(p.bitmap).map((b) => `0x${b.toString(16).padStart(2, '0')}`);
    for (let off = 0; off < hex.length; off += 16) {
      lines.push('  ' + hex.slice(off, off + 16).join(', ') + ',');
    }
    lines.push('};');
    lines.push('');
  }

  lines.push('static constexpr Bitmap kBitmaps[] = {');
  for (const p of phrases) {
    lines.push(
      `  { .width = ${p.width}, .height = ${p.height}, .data = kData_${p.minOfDay} },` +
      `  // min ${p.minOfDay} "${p.text}"`,
    );
  }
  lines.push('};');
  lines.push('');

  // Switch lookup — compiler emits a perfect-hash jump table for a sparse
  // set this small. More readable than a binary-search array of pairs.
  lines.push('const Bitmap* phraseForMinute(int min_of_day) {');
  lines.push('  switch (min_of_day) {');
  for (let i = 0; i < phrases.length; i++) {
    const p = phrases[i]!;
    lines.push(`    case ${p.minOfDay}: return &kBitmaps[${i}];   // "${p.text}"`);
  }
  lines.push('    default: return nullptr;');
  lines.push('  }');
  lines.push('}');
  lines.push('');
  lines.push('}  // namespace fw::night_phrases');
  lines.push('');
  return lines.join('\n');
}

/** 5×5 contact sheet PNG to /tmp/night_phrases_preview.png. */
async function emitSmokeSheet(phrases: BakedPhrase[]): Promise<string> {
  // Each cell renders the bitmap at native size + a 6 px label band below.
  const COLS = 5;
  const ROWS = Math.ceil(phrases.length / COLS);
  const CELL_PAD = 24;
  const LABEL_H = 28;
  const maxW = Math.max(...phrases.map((p) => p.width));
  const maxH = Math.max(...phrases.map((p) => p.height));
  const CELL_W = maxW + CELL_PAD * 2;
  const CELL_H = maxH + LABEL_H + CELL_PAD * 2;
  const SHEET_W = CELL_W * COLS;
  const SHEET_H = CELL_H * ROWS;

  // Build SVG with each phrase rendered as a fresh element, plus a label.
  // SVG → PNG via sharp is the cheapest way to compose 25 sub-images.
  let svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${SHEET_W}" height="${SHEET_H}" viewBox="0 0 ${SHEET_W} ${SHEET_H}">`;
  svg += `<rect width="100%" height="100%" fill="white"/>`;
  for (let i = 0; i < phrases.length; i++) {
    const p = phrases[i]!;
    const col = i % COLS;
    const row = Math.floor(i / COLS);
    const x0 = col * CELL_W;
    const y0 = row * CELL_H;
    // Re-render the bitmap as inline base64 PNG.
    const png = await bitmapToPng(p);
    const dataUri = 'data:image/png;base64,' + png.toString('base64');
    svg += `<image x="${x0 + CELL_PAD}" y="${y0 + CELL_PAD}" width="${p.width}" height="${p.height}" href="${dataUri}"/>`;
    const labelY = y0 + CELL_H - CELL_PAD / 2;
    svg += `<text x="${x0 + CELL_PAD}" y="${labelY}" font-family="monospace" font-size="14" fill="black">${escapeHtml(formatMinLabel(p.minOfDay))} ${escapeHtml(p.text)}</text>`;
    svg += `<rect x="${x0 + CELL_PAD - 1}" y="${y0 + CELL_PAD - 1}" width="${p.width + 2}" height="${p.height + 2}" fill="none" stroke="lightgrey"/>`;
  }
  svg += `</svg>`;

  const out = '/tmp/night_phrases_preview.png';
  await sharp(Buffer.from(svg)).png().toFile(out);
  return out;
}

function formatMinLabel(minOfDay: number): string {
  const h = Math.floor(minOfDay / 60);
  const m = minOfDay % 60;
  return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}`;
}

async function bitmapToPng(p: BakedPhrase): Promise<Buffer> {
  // Expand the 1-bit packed bitmap to an 8-bit grayscale buffer for sharp.
  const rowBytes = Math.ceil(p.width / 8);
  const pixels = Buffer.alloc(p.width * p.height, 255);  // start white
  for (let y = 0; y < p.height; y++) {
    for (let x = 0; x < p.width; x++) {
      const byte = p.bitmap[y * rowBytes + (x >> 3)]!;
      const bit = (byte >> (7 - (x & 7))) & 1;
      if (bit) pixels[y * p.width + x] = 0;             // black
    }
  }
  return sharp(pixels, { raw: { width: p.width, height: p.height, channels: 1 } })
    .png()
    .toBuffer();
}

async function main() {
  const args = new Set(process.argv.slice(2));
  const smokeOnly = args.has('--smoke');

  await fs.access(FONT_PATH).catch(() => {
    throw new Error(`Fraunces font not found at ${FONT_PATH}.`);
  });
  const fontBytes = await fs.readFile(FONT_PATH);
  const fontUrl = 'data:font/woff2;base64,' + fontBytes.toString('base64');

  const eligible = eligibleMinutes();
  if (eligible.length !== 25) {
    throw new Error(`expected 25 partial-eligible minutes; got ${eligible.length}`);
  }

  const browser = await chromium.launch();
  const baked: BakedPhrase[] = [];
  for (const { h, m, minOfDay } of eligible) {
    const text = nightPhrase(h, m);
    process.stdout.write(`baking ${formatMinLabel(minOfDay)} "${text}"... `);
    baked.push(await bakePhrase(browser, minOfDay, text, fontUrl));
    console.log('ok');
  }
  await browser.close();

  if (smokeOnly) {
    const out = await emitSmokeSheet(baked);
    console.log('');
    console.log(`smoke contact sheet → ${out}`);
    return;
  }

  await fs.mkdir(path.dirname(HEADER_PATH), { recursive: true });
  await fs.writeFile(HEADER_PATH, emitHeader());
  await fs.writeFile(SOURCE_PATH, emitSource(baked));

  const totalBytes = baked.reduce((s, p) => s + p.bitmap.length, 0);
  const maxW = Math.max(...baked.map((p) => p.width));
  const maxH = Math.max(...baked.map((p) => p.height));
  console.log('');
  console.log(
    `25 phrases baked  total=${(totalBytes / 1024).toFixed(1)} KB  ` +
    `max-bitmap=${maxW}×${maxH}px  output=${path.relative(process.cwd(), HEADER_PATH)} + .cpp`,
  );
}

main().catch((err) => {
  console.error('bake failed:', err);
  process.exit(1);
});
