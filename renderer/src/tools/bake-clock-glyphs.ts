/**
 * Bake clock-zone digit glyphs into a C++ header for on-device 1-bit partial
 * refresh.
 *
 * Why per-glyph (vs pre-composed strings): the string-bake approach matched
 * the live-face rasterization exactly within its own pipeline, but the live
 * renderer's clock element sits in a different surrounding layout context
 * (parent containers, absolute positioning, inherited cascade) than our
 * isolated bake page. The cumulative sub-pixel offset between the two
 * pipelines was ~2-3 px on the corner clock — visibly worse than the small
 * glyph-composition imperfection. Per-glyph composition with tnum-correct
 * advances gives a closer match in practice.
 *
 * Key fix vs the original glyph bake: render ALL 11 chars together in ONE
 * tnum-enabled span and measure each char's advance via the Range API. The
 * original bake rendered each char in isolation, so tnum (which only fires
 * on multi-digit runs) didn't apply and we got the natural proportional
 * advances of the variable font — '1' came out narrow (58 px), '0' wide
 * (96 px), and the firmware composition produced visibly uneven digit
 * spacing relative to the live face.
 *
 * Outputs:
 *   firmware/src/generated/clock_glyphs.h
 *   firmware/src/generated/clock_glyphs.cpp
 *
 * Run: `npm run bake:clock-glyphs` (in renderer/).
 */

import { chromium, type Browser } from 'playwright';
import sharp from 'sharp';
import fs from 'node:fs/promises';
import path from 'node:path';
import { ROOT } from '../config.js';

interface Preset {
  name: string;
  cppName: string;
  fontSize: number;
  opsz: number;
  weight: number;
  lineHeight: number;
  letterSpacingCss: string;     // e.g. 'normal' or '-0.02em' — matches live face
  letterSpacingPx: number;      // numeric form for firmware cursor offset
}

const PRESETS: Preset[] = [
  // Summary face — Morning's panel-filling 160u Didone clock. 11 glyphs
  // sum to ~12 KB of flash (vs ~233 KB for the abandoned string-bake), so
  // re-including it is essentially free now that we're on the per-glyph
  // path. Without this preset, Morning's 1-min Partial cadence promotes
  // every wake to a Full because presetByFontSize(160) returns nullptr —
  // not what we want.
  {
    name: 'summary',
    cppName: 'kSummaryClock',
    fontSize: 160,
    opsz: 144,
    weight: 500,
    lineHeight: 0.9,
    // Live face uses letter-spacing: -0.02em → 160 * -0.02 = -3.2 px.
    letterSpacingCss: '-0.02em',
    letterSpacingPx: -3,
  },
  {
    name: 'compact',
    cppName: 'kCompactClock',
    fontSize: 44,
    opsz: 72,
    weight: 500,
    lineHeight: 1.0,
    letterSpacingCss: 'normal',
    letterSpacingPx: 0,
  },
  {
    name: 'corner',
    cppName: 'kCornerClock',
    fontSize: 28,
    opsz: 36,
    weight: 500,
    lineHeight: 1.0,
    letterSpacingCss: 'normal',
    letterSpacingPx: 0,
  },
];

const CHARS = ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9', ':'] as const;
const INK_THRESHOLD = 240;

const FIRMWARE_ROOT = path.resolve(ROOT, '..', 'firmware');
const HEADER_PATH = path.join(FIRMWARE_ROOT, 'src/generated/clock_glyphs.h');
const SOURCE_PATH = path.join(FIRMWARE_ROOT, 'src/generated/clock_glyphs.cpp');
const FONT_PATH = path.join(ROOT, 'templates/fonts/Fraunces[opsz,wght].woff2');

interface BakedGlyph {
  char: string;
  width: number;
  height: number;
  leftBearing: number;    // ink-left offset from cursor advance origin
  topBearing: number;     // ink-top above baseline (positive = above)
  advance: number;        // tnum advance for digits, natural for ':'
  bitmap: Buffer;         // 1bpp, MSB-first, row-padded to byte boundary
}

interface BakedPreset {
  preset: Preset;
  fontSizePx: number;
  lineHeightPx: number;
  baselineFromTopPx: number;
  glyphs: BakedGlyph[];   // 11 entries, indexed by CHARS order
}

async function bakePreset(browser: Browser, preset: Preset, fontUrl: string): Promise<BakedPreset> {
  const stylesheet = `
    @font-face {
      font-family: 'Fraunces';
      src: url('${fontUrl}') format('woff2-variations');
      font-weight: 100 900;
      font-display: block;
    }
    html, body {
      margin: 0; padding: 0; background: white;
      -webkit-font-smoothing: antialiased;
      text-rendering: geometricPrecision;
    }
    #wrap {
      display: inline-block;
      padding: ${preset.fontSize}px;
      background: white;
    }
    #zone {
      display: inline-block;
      font-family: 'Fraunces';
      font-variation-settings: 'opsz' ${preset.opsz}, 'wght' ${preset.weight};
      font-feature-settings: 'tnum' 1;
      font-size: ${preset.fontSize}px;
      line-height: ${preset.lineHeight};
      letter-spacing: ${preset.letterSpacingCss};
      color: black;
      white-space: nowrap;
    }
    /* Baseline marker — 1×1 inline-block, vertical-align: baseline → its
       bottom edge sits ON the line's baseline. Lets us compute the absolute
       baseline y-coord of the rendered text. */
    #bm {
      display: inline-block;
      vertical-align: baseline;
      width: 1px;
      height: 1px;
      background: white;
    }
  `;

  // DPR=1 matches the live renderer (renderer/src/config.ts).
  const page = await browser.newPage({ deviceScaleFactor: 1 });
  // Render all 11 chars in one tnum-enabled string. This gives correct
  // tabular advances per char (tnum requires a multi-char run to engage).
  const text = CHARS.join('');
  const html = `<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>${stylesheet}</style></head>
<body><div id="wrap"><span id="zone">${text}</span><span id="bm"></span></div></body></html>`;
  await page.setContent(html);
  await page.evaluate(() => document.fonts.ready);

  const measurements = await page.evaluate(() => {
    const zone = document.getElementById('zone') as HTMLElement;
    const bm = document.getElementById('bm') as HTMLElement;
    const textNode = zone.firstChild as Text;
    const z = zone.getBoundingClientRect();
    const baselineY = bm.getBoundingClientRect().bottom;
    const ranges: Array<{ x: number; y: number; w: number; h: number }> = [];
    for (let i = 0; i < (textNode.data ?? '').length; i++) {
      const range = document.createRange();
      range.setStart(textNode, i);
      range.setEnd(textNode, i + 1);
      const r = range.getBoundingClientRect();
      ranges.push({ x: r.x, y: r.y, w: r.width, h: r.height });
    }
    return { zoneX: z.x, zoneY: z.y, baselineY, ranges };
  });

  const png = await page.screenshot({ omitBackground: false, fullPage: true });
  const raw = await sharp(png)
    .grayscale()
    .raw()
    .toBuffer({ resolveWithObject: true });
  const W = raw.info.width;
  const H = raw.info.height;
  const data = raw.data;
  await page.close();

  const glyphs: BakedGlyph[] = [];
  for (let i = 0; i < CHARS.length; i++) {
    const ch = CHARS[i]!;
    const r = measurements.ranges[i]!;

    // Cell box in screenshot pixel coords. The cell width = tnum advance.
    const cellLeft = Math.floor(r.x);
    const cellRight = Math.min(W, Math.ceil(r.x + r.w));
    // Vertical search bounds: extend up to capture ascenders that may go
    // above the range bbox, and down for descenders below.
    const cellTop = 0;
    const cellBottom = H;

    let minX = cellRight, maxX = cellLeft - 1, minY = cellBottom, maxY = cellTop - 1;
    for (let y = cellTop; y < cellBottom; y++) {
      for (let x = cellLeft; x < cellRight; x++) {
        if (data[y * W + x]! < INK_THRESHOLD) {
          if (x < minX) minX = x;
          if (x > maxX) maxX = x;
          if (y < minY) minY = y;
          if (y > maxY) maxY = y;
        }
      }
    }
    if (maxX < minX || maxY < minY) {
      throw new Error(`No ink found for char '${ch}' in preset ${preset.name}`);
    }

    const w = maxX - minX + 1;
    const h = maxY - minY + 1;
    const rowBytes = Math.ceil(w / 8);
    const bitmap = Buffer.alloc(rowBytes * h);
    for (let y = 0; y < h; y++) {
      for (let x = 0; x < w; x++) {
        if (data[(minY + y) * W + (minX + x)]! < INK_THRESHOLD) {
          bitmap[y * rowBytes + (x >> 3)]! |= 0x80 >> (x & 7);
        }
      }
    }

    glyphs.push({
      char: ch,
      width: w,
      height: h,
      leftBearing: minX - cellLeft,
      topBearing: Math.round(measurements.baselineY) - minY,
      advance: Math.round(r.w),
      bitmap,
    });
  }

  const baselineFromTopPx = Math.round(measurements.baselineY) - Math.round(measurements.zoneY);
  const lineHeightPx = Math.round(preset.fontSize * preset.lineHeight);

  return {
    preset,
    fontSizePx: preset.fontSize,
    lineHeightPx,
    baselineFromTopPx,
    glyphs,
  };
}

function escapeChar(c: string): string {
  return c;  // ':' and digits are all safe in C-style block comments.
}

function emitHeader(): string {
  return `// firmware/src/generated/clock_glyphs.h
//
// AUTO-GENERATED by renderer/src/tools/bake-clock-glyphs.ts. Do not edit.
//
#pragma once

#include <cstdint>

namespace fw::clock {

// Tight bitmap descriptor for one glyph. 1bpp, MSB-first, row-padded.
struct GlyphMeta {
  uint16_t width;
  uint16_t height;
  int16_t  left_bearing;   // ink-left offset from cursor advance origin
  int16_t  top_bearing;    // ink-top above baseline
  uint16_t advance;        // cursor advance after rendering this glyph
  uint32_t bitmap_offset;  // offset into Preset::bitmap_data
  uint16_t bitmap_bytes;
};

struct Preset {
  uint16_t font_size_px;
  uint16_t line_height_px;
  uint16_t baseline_from_top_px;
  int16_t  letter_spacing_px;
  GlyphMeta glyphs[11];    // indexed 0..9 for digits, 10 for ':'
  const uint8_t* bitmap_data;
  uint32_t bitmap_data_bytes;
};

inline constexpr int glyphIndex(char c) {
  if (c >= '0' && c <= '9') return c - '0';
  if (c == ':') return 10;
  return -1;
}

${PRESETS.map((p) => `extern const Preset ${p.cppName};`).join('\n')}

}  // namespace fw::clock
`;
}

function emitSource(baked: BakedPreset[]): string {
  const lines: string[] = [];
  lines.push('// firmware/src/generated/clock_glyphs.cpp');
  lines.push('// AUTO-GENERATED by renderer/src/tools/bake-clock-glyphs.ts. Do not edit.');
  lines.push('');
  lines.push('#include "clock_glyphs.h"');
  lines.push('');
  lines.push('namespace fw::clock {');
  lines.push('');

  for (const bp of baked) {
    const chunks: Buffer[] = [];
    const offsets: number[] = [];
    let cursor = 0;
    for (const g of bp.glyphs) {
      offsets.push(cursor);
      chunks.push(g.bitmap);
      cursor += g.bitmap.length;
    }
    const data = Buffer.concat(chunks);

    lines.push(`// ----- ${bp.preset.cppName} -----`);
    lines.push(`static const uint8_t ${bp.preset.cppName}Data[] = {`);
    for (let gi = 0; gi < bp.glyphs.length; gi++) {
      const g = bp.glyphs[gi]!;
      const off = offsets[gi]!;
      lines.push(`  // '${escapeChar(g.char)}' — offset ${off}, ${g.bitmap.length} bytes (${g.width}×${g.height})`);
      const hex = Array.from(g.bitmap).map((b) => `0x${b.toString(16).padStart(2, '0')}`);
      for (let i = 0; i < hex.length; i += 16) {
        lines.push('  ' + hex.slice(i, i + 16).join(', ') + ',');
      }
    }
    lines.push('};');
    lines.push('');

    lines.push(`const Preset ${bp.preset.cppName} = {`);
    lines.push(`  .font_size_px = ${bp.fontSizePx},`);
    lines.push(`  .line_height_px = ${bp.lineHeightPx},`);
    lines.push(`  .baseline_from_top_px = ${bp.baselineFromTopPx},`);
    lines.push(`  .letter_spacing_px = ${bp.preset.letterSpacingPx},`);
    lines.push(`  .glyphs = {`);
    for (let gi = 0; gi < bp.glyphs.length; gi++) {
      const g = bp.glyphs[gi]!;
      const off = offsets[gi]!;
      lines.push(
        `    { .width = ${g.width}, .height = ${g.height}, ` +
        `.left_bearing = ${g.leftBearing}, .top_bearing = ${g.topBearing}, ` +
        `.advance = ${g.advance}, .bitmap_offset = ${off}, ` +
        `.bitmap_bytes = ${g.bitmap.length} },  // '${escapeChar(g.char)}'`,
      );
    }
    lines.push(`  },`);
    lines.push(`  .bitmap_data = ${bp.preset.cppName}Data,`);
    lines.push(`  .bitmap_data_bytes = ${data.length},`);
    lines.push('};');
    lines.push('');
  }

  lines.push('}  // namespace fw::clock');
  lines.push('');
  return lines.join('\n');
}

async function main() {
  await fs.access(FONT_PATH).catch(() => {
    throw new Error(`Fraunces font not found at ${FONT_PATH}.`);
  });
  const fontBytes = await fs.readFile(FONT_PATH);
  const fontUrl = 'data:font/woff2;base64,' + fontBytes.toString('base64');

  const browser = await chromium.launch();
  const baked: BakedPreset[] = [];
  for (const preset of PRESETS) {
    process.stdout.write(`baking '${preset.name}' (${preset.fontSize}px, opsz ${preset.opsz})... `);
    baked.push(await bakePreset(browser, preset, fontUrl));
    console.log('ok');
  }
  await browser.close();

  await fs.mkdir(path.dirname(HEADER_PATH), { recursive: true });
  await fs.writeFile(HEADER_PATH, emitHeader());
  await fs.writeFile(SOURCE_PATH, emitSource(baked));

  console.log('');
  for (const bp of baked) {
    const totalBytes = bp.glyphs.reduce((s, g) => s + g.bitmap.length, 0);
    const tnumAdvance = bp.glyphs[0]!.advance;
    const colonAdvance = bp.glyphs[10]!.advance;
    console.log(
      `  ${bp.preset.cppName}: line_height=${bp.lineHeightPx}px baseline=${bp.baselineFromTopPx}px ` +
      `data=${totalBytes}B tnum_advance=${tnumAdvance}px colon_advance=${colonAdvance}px`,
    );
  }
}

main().catch((err) => {
  console.error('bake failed:', err);
  process.exit(1);
});
