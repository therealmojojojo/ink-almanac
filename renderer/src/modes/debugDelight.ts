/**
 * Debug variants of the Summary face used to spot-check the two long-form
 * text cells at non-default sizing:
 *   - bilingual haiku/tanka delight cell (`/debug/delight-test*`)
 *   - smart-pill word-study cell        (`/debug/smart-pill-test*`)
 *
 * Not wired into the production face rotation. Loads corpus text directly,
 * synthesises a SummaryInput around it (real clock + the existing
 * weather/smart_pill/device inputs so the cell renders in real face context),
 * and post-processes the HTML to inject CSS overrides for the cell under
 * test.
 */
import fs from 'node:fs/promises';
import path from 'node:path';
import { ROOT } from '../config.js';
import { loadInput, requireInput, MissingInputError } from '../inputs.js';
import { SCHEMAS } from './schema.js';
import * as summary from './summary.js';
import type { ModePrepared } from './index.js';

const CORPUS = path.resolve(ROOT, '..', 'corpus');
const TEXT_DIRS = ['texts', 'personal_library'];

export interface DelightTestOptions {
  /** Corpus text id (filename without `.yaml`). Must be a haiku/tanka with
   *  both `text_variants.en` and `text_variants.ja`. */
  id: string;
  /** JA font-size override in `u`. Default 32 (vs production 40). */
  jaSize?: number;
  /** EN font-size override in `u`. Default 30 (vs production 32). */
  enSize?: number;
  /** Shared line-height in `u`. Default keeps the production 56u; pass a
   *  value if you want to test tighter row rhythm too. */
  lineHeight?: number;
}

interface HaikuDoc {
  id: string;
  form: 'haiku' | 'tanka';
  title?: string;
  author?: string;
  year?: string;
  en: string;
  ja: string;
}

interface CorpusText {
  id: string;
  form?: string;
  title?: string;
  author?: string;
  year?: string;
  variants: Record<string, string>;
  smart_pill_body?: string;
}

/** Minimal corpus-YAML reader. Mirrors validate-corpus-fit's parser shape;
 *  only extracts the fields the Summary delight needs.
 *
 *  Note: doesn't depend on a real YAML parser — js-yaml isn't a dep of the
 *  renderer and pulling it in for one debug endpoint isn't worth it. The
 *  real corpus tooling lives in `pairing/` (Python) and uses PyYAML. */
async function loadCorpusText(id: string): Promise<CorpusText> {
  for (const sub of TEXT_DIRS) {
    const p = path.join(CORPUS, sub, `${id}.yaml`);
    let raw: string;
    try {
      raw = await fs.readFile(p, 'utf8');
    } catch (err) {
      if ((err as NodeJS.ErrnoException).code === 'ENOENT') continue;
      throw err;
    }
    return parseCorpusYaml(raw, id);
  }
  throw new Error(`text '${id}' not found in corpus/{${TEXT_DIRS.join(',')}}/`);
}

async function loadHaiku(id: string): Promise<HaikuDoc> {
  const t = await loadCorpusText(id);
  const h = toHaikuDoc(t, id);
  if (!h) throw new Error(`${id}: not a bilingual haiku/tanka (need form + text_variants.{en,ja})`);
  return h;
}

async function loadSmartPillText(id: string): Promise<{ doc: CorpusText; body: string }> {
  const t = await loadCorpusText(id);
  if (!t.smart_pill_body) {
    throw new Error(`${id}: no smart_pill.body in YAML`);
  }
  return { doc: t, body: t.smart_pill_body };
}

/** Find the first unescaped close-quote of style `q` in `s`. Inside
 *  single-quoted scalars, '' escapes a literal single quote — we skip
 *  consecutive pairs. Inside double-quoted scalars, \" is the escape. */
function findCloseQuote(s: string, q: string): number {
  let i = 0;
  while (i < s.length) {
    const c = s[i];
    if (q === "'" && c === "'") {
      if (s[i + 1] === "'") { i += 2; continue; }  // escape
      return i;
    }
    if (q === '"' && c === '"') {
      // Walk back; if preceded by an odd number of backslashes, escaped.
      let bs = 0;
      for (let j = i - 1; j >= 0 && s[j] === '\\'; j--) bs++;
      if (bs % 2 === 0) return i;
    }
    i++;
  }
  return -1;
}

function unescapeQuoted(s: string, q: string): string {
  if (q === "'") return s.replace(/''/g, "'");
  return s.replace(/\\(.)/g, (_m, c) => {
    if (c === 'n') return '\n';
    if (c === 't') return '\t';
    return c;
  });
}

/** Minimal corpus-YAML parser — extracts the fields the debug endpoints
 *  consume: top-level scalars (id/form/title/author/year), `text_variants`,
 *  and `smart_pill.body`. Handles PyYAML's three output shapes for body
 *  values: block scalars (`|` / `|-`), single-quoted (multi-line capable
 *  with `''` escape), and plain. Not a general YAML parser. */
function parseCorpusYaml(raw: string, fallbackId: string): CorpusText {
  const lines = raw.split('\n');
  const top: Record<string, string> = {};
  const variants: Record<string, string> = {};
  let smartPillBody: string | undefined;
  let i = 0;
  while (i < lines.length) {
    const line = lines[i]!;
    const m = line.match(/^(id|form|title|author|year):\s*(.+?)\s*$/);
    if (m) {
      top[m[1]!] = m[2]!.replace(/^["']|["']$/g, '');
      i++; continue;
    }
    if (/^text_variants:\s*$/.test(line)) {
      i++;
      while (i < lines.length) {
        // Three PyYAML output shapes for the body value:
        //   en: |    → block scalar (folded body lines below at ≥4 indent)
        //   en: 'xxx (multi-line) ... '   → single-quoted, can span lines
        //   en: "xxx" / unquoted          → plain or double-quoted (rare)
        const head = lines[i]!.match(/^  ([a-z]{2,3}):\s*(.*)$/);
        if (!head) break;
        const lang = head[1]!;
        const rest = head[2]!;
        if (/^\|[-+]?\s*$/.test(rest)) {
          // Block scalar.
          i++;
          const body: string[] = [];
          while (i < lines.length) {
            const bl = lines[i]!;
            if (bl.startsWith('    ')) body.push(bl.slice(4));
            else if (bl.trim() === '') body.push('');
            else break;
            i++;
          }
          variants[lang] = body.join('\n').replace(/\n+$/, '');
          continue;
        }
        if (rest.startsWith("'") || rest.startsWith('"')) {
          const q = rest[0]!;
          // Read a possibly-multi-line quoted scalar. Inside single quotes,
          // '' is the escape for a literal '. Adjacent non-blank input
          // lines are joined as separate output lines (preserving the
          // haiku/stanza shape PyYAML preserves via blank-line separators).
          const nonBlank: string[] = [];
          let cursor = rest.slice(1);
          let done = false;
          // Scan the rest of the first line for an unescaped close-quote.
          const closeOnFirst = findCloseQuote(cursor, q);
          if (closeOnFirst >= 0) {
            const content = cursor.slice(0, closeOnFirst);
            if (content.trim()) nonBlank.push(unescapeQuoted(content, q));
            done = true;
          } else if (cursor.trim()) {
            nonBlank.push(unescapeQuoted(cursor, q));
          }
          i++;
          while (!done && i < lines.length) {
            const ln = lines[i]!;
            const trimmed = ln.trim();
            const closeIdx = trimmed === '' ? -1 : findCloseQuote(trimmed, q);
            if (closeIdx >= 0) {
              const before = trimmed.slice(0, closeIdx);
              if (before.trim()) nonBlank.push(unescapeQuoted(before.trim(), q));
              i++;
              done = true;
              break;
            }
            if (trimmed !== '') nonBlank.push(unescapeQuoted(trimmed, q));
            i++;
          }
          variants[lang] = nonBlank.join('\n');
          continue;
        }
        // Plain unquoted scalar — treat as single-line.
        if (rest.trim()) {
          variants[lang] = rest.trim();
          i++;
          continue;
        }
        i++;
      }
      continue;
    }
    if (/^smart_pill:\s*$/.test(line)) {
      i++;
      while (i < lines.length) {
        const bl = lines[i]!;
        if (!bl.startsWith('  ')) break;
        // body can be a quoted scalar on the same line OR a block under `body: |`
        const sameLineRaw = bl.match(/^  body:\s*(.+?)\s*$/);
        const blockHeader = /^  body:\s*\|[-+]?\s*$/.test(bl);
        if (sameLineRaw && !blockHeader) {
          // Single- or double-quoted scalar (PyYAML default for a string
          // with no newlines). Inside single quotes, '' is the escape for
          // a literal single quote — undo it. Defensive of multi-line
          // continuation, though pill bodies in the corpus are one-liners.
          const firstChar = sameLineRaw[1]![0];
          let body: string;
          if (firstChar === "'" || firstChar === '"') {
            const q = firstChar;
            // Walk forward until we hit the closing quote, joining
            // continuation lines with a space (YAML folded-style).
            let acc = sameLineRaw[1]!.slice(1);
            i++;
            while (!new RegExp(`(^|[^${q}])${q}\\s*$`).test(acc)) {
              if (i >= lines.length) break;
              acc += ' ' + (lines[i]!.trimStart());
              i++;
            }
            body = acc.replace(new RegExp(`${q}\\s*$`), '');
            if (q === "'") body = body.replace(/''/g, "'");
            else body = body.replace(/\\"/g, '"').replace(/\\\\/g, '\\');
          } else {
            // Plain unquoted scalar
            body = sameLineRaw[1]!;
            i++;
            while (i < lines.length) {
              const nx = lines[i]!;
              if (nx.startsWith('    ')) {
                body += ' ' + nx.trimStart();
                i++;
                continue;
              }
              break;
            }
          }
          smartPillBody = body;
          continue;
        }
        if (blockHeader) {
          i++;
          const body: string[] = [];
          while (i < lines.length) {
            const nx = lines[i]!;
            if (nx.startsWith('    ')) body.push(nx.slice(4));
            else if (nx.trim() === '') body.push('');
            else break;
            i++;
          }
          smartPillBody = body.join('\n').replace(/\n+$/, '');
          continue;
        }
        i++;
      }
      continue;
    }
    i++;
  }
  const out: CorpusText = {
    id: top['id'] || fallbackId,
    variants,
  };
  if (top['form']) out.form = top['form'];
  if (top['title']) out.title = top['title'];
  if (top['author']) out.author = top['author'];
  if (top['year']) out.year = top['year'];
  if (smartPillBody) out.smart_pill_body = smartPillBody;
  return out;
}

function toHaikuDoc(t: CorpusText, fallbackId: string): HaikuDoc | null {
  const form = t.form;
  if ((form !== 'haiku' && form !== 'tanka') || !t.variants['en'] || !t.variants['ja']) {
    return null;
  }
  const out: HaikuDoc = {
    id: t.id || fallbackId,
    form,
    en: t.variants['en']!,
    ja: t.variants['ja']!,
  };
  if (t.title) out.title = t.title;
  if (t.author) out.author = t.author;
  if (t.year) out.year = t.year;
  return out;
}

/** Build a synthetic Summary input where the delight cell holds the supplied
 *  bilingual haiku. Other zones (weather/smart_pill/clock/device) come from
 *  the renderer's current `inputs/` so the face renders in real context. */
async function gatherSummaryWithDelight(haiku: HaikuDoc): Promise<unknown> {
  const weather = await requireInput('weather');
  const smart_pill = await requireInput('smart_pill');
  const sonos = await loadInput('sonos');
  const device = await loadInput('device');

  // Use server clock (same source as the production summary mode).
  const now = new Date();
  const tz = process.env.INKPLATE_RENDER_TZ || undefined;
  const time = new Intl.DateTimeFormat('en-GB', {
    hour: '2-digit', minute: '2-digit', hour12: false, timeZone: tz,
  }).format(now);
  const date = `${new Intl.DateTimeFormat('en-US', { weekday: 'long', timeZone: tz }).format(now)} · ${
    new Intl.DateTimeFormat('en-US', { month: 'long', day: 'numeric', timeZone: tz }).format(now)
  }`;

  // Pull the existing pairing for the gallery side, then override gallery
  // flavor + companion so the delight cell renders our haiku.
  const existingPairing = await requireInput('pairing') as Record<string, unknown>;
  const galleryAny = (existingPairing.gallery ?? {}) as Record<string, unknown>;
  const pairing = {
    ...existingPairing,
    gallery: {
      ...galleryAny,
      flavor: 'visual',
      // visual is required when flavor=visual; reuse whatever's currently in
      // the pairing input. If none, ditherMask handles `flavor=visual` without
      // a visual block (it just no-ops the mask).
      visual: galleryAny.visual,
      companion: {
        kind: 'text',
        form: haiku.form,
        body: haiku.en,
        body_ja: haiku.ja,
        poet: haiku.author ?? '—',
        ...(haiku.title ? { title: haiku.title } : {}),
        ...(haiku.year ? { dates: haiku.year } : {}),
        language: 'en',
      },
    },
  };

  return { clock: { time, date }, weather, smart_pill, pairing, sonos, device };
}

/** Inject a `<style>` block at the end of the document head (before `</head>`)
 *  that overrides the JA/EN font sizes (and optionally the shared line-
 *  height) on the anthology delight layout. Higher specificity than the
 *  production rules in summary.css, no source edit needed. */
function injectSizeOverride(html: string, jaSize: number, enSize: number, lineHeight?: number): string {
  const lh = lineHeight ?? null;
  const css = `
<style data-debug="delight-test">
  .summary-delight.anthology .body .ja {
    font-size: calc(${jaSize} * var(--u)) !important;${
    lh ? `\n    line-height: calc(${lh} * var(--u)) !important;` : ''
  }
  }
  .summary-delight.anthology .body .en {
    font-size: calc(${enSize} * var(--u)) !important;${
    lh ? `\n    line-height: calc(${lh} * var(--u)) !important;` : ''
  }
  }
</style>
`;
  if (html.includes('</head>')) {
    return html.replace('</head>', `${css}</head>`);
  }
  // Fallback: insert after <body> if no head close tag present.
  return html.replace('<body>', `<body>${css}`);
}

/** Width (in `u`) the JA + EN body would occupy at the supplied sizes,
 *  matching the audit script's prediction model. Compare against 609u
 *  (the delight body's inner width) to decide overflow.
 *
 *  Constants (40u col-gap, 0.5 Fraunces char-width) match
 *  `pairing/audit_text_readability.py`. Keep in sync. */
export function predictAnthologyWidth(ja: string, en: string, jaSize: number, enSize: number): {
  ja_max: number; en_max: number; width: number; budget: number; lineMismatch: boolean;
} {
  const jaLines = ja.split('\n').filter((l) => l.trim().length > 0);
  const enLines = en.split('\n').filter((l) => l.trim().length > 0);
  const ja_max = jaLines.reduce((m, l) => Math.max(m, [...l].length), 0);
  const en_max = enLines.reduce((m, l) => Math.max(m, l.length), 0);
  const width = Math.round(ja_max * jaSize + 40 + en_max * enSize * 0.5);
  return { ja_max, en_max, width, budget: 609, lineMismatch: jaLines.length !== enLines.length };
}

/** Walk the corpus once and return every text. Cheap; no per-call walk. */
async function listAllCorpusTexts(): Promise<CorpusText[]> {
  const out: CorpusText[] = [];
  for (const sub of TEXT_DIRS) {
    const dir = path.join(CORPUS, sub);
    let names: string[];
    try {
      names = await fs.readdir(dir);
    } catch {
      continue;
    }
    for (const name of names) {
      if (!name.endsWith('.yaml') || name.startsWith('EXAMPLE')) continue;
      const raw = await fs.readFile(path.join(dir, name), 'utf8');
      out.push(parseCorpusYaml(raw, name.replace(/\.yaml$/, '')));
    }
  }
  return out;
}

/** Bilingual haiku/tanka — used by the delight overflow grid. */
export async function listBilingualHaiku(): Promise<HaikuDoc[]> {
  const all = await listAllCorpusTexts();
  const out: HaikuDoc[] = [];
  for (const t of all) {
    const h = toHaikuDoc(t, t.id);
    if (h) out.push(h);
  }
  out.sort((a, b) => a.id.localeCompare(b.id));
  return out;
}

/** Texts that carry an authored smart-pill body — used by the smart-pill
 *  overflow grid. */
export async function listSmartPillTexts(): Promise<Array<{ id: string; form?: string; title?: string; author?: string; body: string }>> {
  const all = await listAllCorpusTexts();
  const out: Array<{ id: string; form?: string; title?: string; author?: string; body: string }> = [];
  for (const t of all) {
    if (!t.smart_pill_body) continue;
    const item: { id: string; form?: string; title?: string; author?: string; body: string } = {
      id: t.id,
      body: t.smart_pill_body,
    };
    if (t.form) item.form = t.form;
    if (t.title) item.title = t.title;
    if (t.author) item.author = t.author;
    out.push(item);
  }
  out.sort((a, b) => a.id.localeCompare(b.id));
  return out;
}

// --- smart-pill geometry ---------------------------------------------------
// Mirrors `summary.ts`'s `smartPillFontSize` constants. The cell is a fixed
// 437×408 box with IBM Plex Sans, line-height ratio 1.35 in production. The
// `.summary-smart-pill .body { padding-bottom: 8u }` is the only vertical-pad
// addition the override can claw back; with `pad=0` we strip that and switch
// the pill flex from `justify-content: center` to `flex-start` so any short
// bodies top-align rather than visually float.
const PILL_W = 437;
const PILL_H = 408;
// Empirical char-width factor for IBM Plex Sans rendered with text-align:
// justify and hyphens: auto. The production size-picker in summary.ts uses
// 0.55 (a conservative average across the alphabet); that's deliberately
// pessimistic so the auto-ladder over-shrinks rather than under. For the
// audit predictor we want the factor that *matches what the browser
// actually paints* — at justify+hyphens, lines pack ~10% denser than the
// alphabet-average factor implies. 0.50 matches operator-verified renders
// (e.g. valery-poem-never-finished at 28u/lh=1.1/pad=1/grow=60u: model
// says 35cpl × 13r = 455-char capacity, body is 450 — fits with a
// hair to spare, matching what the browser shows).
const PILL_CHAR_W = 0.50;
const PILL_ITEM_PAD_BOTTOM = 8;
const PILL_DEFAULT_LH = 1.35;

export interface SmartPillFitParams {
  size: number;       // u
  lineHeight: number; // unitless ratio
  pad: boolean;
}

export function predictSmartPillFit(body: string, p: SmartPillFitParams) {
  const charsPerLine = Math.floor(PILL_W / (p.size * PILL_CHAR_W));
  const usableHeight = PILL_H - (p.pad ? PILL_ITEM_PAD_BOTTOM : 0);
  // Round, not floor: the trailing fractional row's descender fits inside
  // the remaining padding space in practice. Floor was losing a full row
  // of capacity (e.g. 12.99 → 12 instead of 13 at 28u/lh=1.1/pad=1).
  const rows = Math.round(usableHeight / (p.size * p.lineHeight));
  const capacity = Math.max(0, charsPerLine) * Math.max(0, rows);
  return {
    chars: body.length,
    charsPerLine,
    rows,
    capacity,
    overflow: body.length > capacity,
    over: body.length - capacity,
    usableHeight,
  };
}

export interface SmartPillTestOptions {
  /** Corpus text id with a `smart_pill.body`. */
  id: string;
  /** Forced body font-size in `u`. Default 30 (operator's sweet-spot floor). */
  size?: number;
  /** Body line-height as a unitless ratio. Default 1.35 (production). */
  lineHeight?: number;
  /** When false (`pad=0`), strips `.body { padding-bottom: 8u }` and switches
   *  `.summary-smart-pill { justify-content }` from `center` to `flex-start`.
   *  Default true. */
  pad?: boolean;
}

/** Synthesise a SummaryInput where `smart_pill.body` carries the supplied
 *  pill body. Other zones come from the renderer's current `inputs/`. */
async function gatherSummaryWithPill(body: string): Promise<unknown> {
  const weather = await requireInput('weather');
  const sonos = await loadInput('sonos');
  const device = await loadInput('device');
  const pairing = await requireInput('pairing');

  const now = new Date();
  const tz = process.env.INKPLATE_RENDER_TZ || undefined;
  const time = new Intl.DateTimeFormat('en-GB', {
    hour: '2-digit', minute: '2-digit', hour12: false, timeZone: tz,
  }).format(now);
  const date = `${new Intl.DateTimeFormat('en-US', { weekday: 'long', timeZone: tz }).format(now)} · ${
    new Intl.DateTimeFormat('en-US', { month: 'long', day: 'numeric', timeZone: tz }).format(now)
  }`;

  // Override smart_pill so the pill cell shows the body under test, regardless
  // of what's currently in `inputs/smart_pill.json`.
  const smart_pill = { body };

  return { clock: { time, date }, weather, smart_pill, pairing, sonos, device };
}

function injectPillOverride(
  html: string,
  size: number,
  lineHeight: number,
  pad: boolean,
): string {
  const padCss = pad
    ? ''
    : `
  .summary-smart-pill { justify-content: flex-start !important; }
  .summary-smart-pill .body { padding-bottom: 0 !important; }`;
  const css = `
<style data-debug="smart-pill-test">
  .summary-smart-pill .body {
    font-size: calc(${size} * var(--u)) !important;
    line-height: ${lineHeight} !important;
  }${padCss}
</style>
`;
  if (html.includes('</head>')) return html.replace('</head>', `${css}</head>`);
  return html.replace('<body>', `<body>${css}`);
}

export async function prepareSmartPillTest(opts: SmartPillTestOptions): Promise<ModePrepared> {
  const { body } = await loadSmartPillText(opts.id);
  const raw = await gatherSummaryWithPill(body);
  const input = SCHEMAS.summary.parse(raw);
  const html = summary.buildHtml(input, 'a');
  const patched = injectPillOverride(
    html,
    opts.size ?? 30,
    opts.lineHeight ?? PILL_DEFAULT_LH,
    opts.pad ?? true,
  );
  return { html: patched, dither: summary.ditherMask(input) };
}

/** Render the production summary face for a single corpus text id, putting
 *  that text's body in the delight cell and its smart_pill body in the pill
 *  cell. Used by the truncation-audit review page so each item is shown the
 *  same way it would appear on the device when this text is the daily
 *  summary slot. No CSS overrides — production geometry. */
async function gatherSummaryWithTextAndPill(text: CorpusText, pillBody: string): Promise<unknown> {
  const weather = await requireInput('weather');
  const sonos = await loadInput('sonos');
  const device = await loadInput('device');
  const existingPairing = await requireInput('pairing') as Record<string, unknown>;
  const galleryAny = (existingPairing.gallery ?? {}) as Record<string, unknown>;

  const now = new Date();
  const tz = process.env.INKPLATE_RENDER_TZ || undefined;
  const time = new Intl.DateTimeFormat('en-GB', {
    hour: '2-digit', minute: '2-digit', hour12: false, timeZone: tz,
  }).format(now);
  const date = `${new Intl.DateTimeFormat('en-US', { weekday: 'long', timeZone: tz }).format(now)} · ${
    new Intl.DateTimeFormat('en-US', { month: 'long', day: 'numeric', timeZone: tz }).format(now)
  }`;

  const en = text.variants['en'] ?? Object.values(text.variants)[0] ?? '';
  const ja = text.variants['ja'];
  const companion: Record<string, unknown> = {
    kind: 'text',
    form: text.form ?? 'aphorism',
    body: en,
    poet: text.author ?? '—',
    language: 'en',
  };
  if (ja && ja.trim().length > 0) companion.body_ja = ja;
  if (text.title) companion.title = text.title;
  if (text.year) companion.dates = text.year;

  const pairing = {
    ...existingPairing,
    gallery: {
      ...galleryAny,
      flavor: 'visual',
      visual: galleryAny.visual,
      companion,
    },
  };
  const smart_pill = { body: pillBody };
  return { clock: { time, date }, weather, smart_pill, pairing, sonos, device };
}

export async function prepareTextSummaryTest(id: string): Promise<ModePrepared> {
  const text = await loadCorpusText(id);
  const pillBody = text.smart_pill_body ?? '';
  const raw = await gatherSummaryWithTextAndPill(text, pillBody);
  const input = SCHEMAS.summary.parse(raw);
  const html = summary.buildHtml(input, 'a');
  return { html, dither: summary.ditherMask(input) };
}

export async function prepareDelightTest(opts: DelightTestOptions): Promise<ModePrepared> {
  const haiku = await loadHaiku(opts.id);
  const raw = await gatherSummaryWithDelight(haiku);
  const input = SCHEMAS.summary.parse(raw);
  const html = summary.buildHtml(input, 'a');
  const patched = injectSizeOverride(
    html,
    opts.jaSize ?? 32,
    opts.enSize ?? 30,
    opts.lineHeight,
  );
  return {
    html: patched,
    dither: summary.ditherMask(input),
  };
}

export { MissingInputError };

// =========================================================================
// Unified face-test: per-triplet preview + dominance-filtered grid.
//
// Each card on the grid is one corpus triplet, rendered with that triplet's
// real summary-slot text in the delight cell (visual-day only) and the same
// text's smart_pill body in the pill cell — i.e. an actual content pair as
// the publisher would push to the renderer on that day.
//
// Parameters cover both cells together:
//   - delight_size  : override per-form static delight body size (non-bilingual)
//   - ja, en        : bilingual JA / EN sizes
//   - pill_size     : pill body font-size
//   - pill_lh       : pill line-height (unitless ratio)
//   - pill_pad      : 1 keeps production padding-bottom + center; 0 strips both
//   - pill_grow_u   : shift the bottom-band boundary in 30u steps; positive
//                     widens the pill, narrows the delight (sum stays 1076u).
//
// Dominance filter (per zone shape, applied to the overflow set):
//   - pill: argmax body length. If the longest body fits at current params,
//     every other pill fits too.
//   - bilingual delight: Pareto frontier on (ja_max, en_max).
//   - monolingual delight: Pareto frontier on (lines, max_chars).
// =========================================================================

interface Triplet {
  id: string;
  summarySlot: string;
  flavor: 'visual-day' | 'text-day';
}

async function listTriplets(): Promise<Triplet[]> {
  const dir = path.join(CORPUS, '_triplets');
  const out: Triplet[] = [];
  let names: string[];
  try {
    names = await fs.readdir(dir);
  } catch {
    return out;
  }
  for (const name of names) {
    if (!name.endsWith('.yaml') || name.startsWith('EXAMPLE')) continue;
    const raw = await fs.readFile(path.join(dir, name), 'utf8');
    const id = raw.match(/^id:\s*(.+?)\s*$/m)?.[1];
    const summarySlot = raw.match(/^summary:\s*(.+?)\s*$/m)?.[1];
    const flavor = raw.match(/^flavor:\s*(.+?)\s*$/m)?.[1];
    if (!id || !summarySlot) continue;
    if (flavor !== 'visual-day' && flavor !== 'text-day') continue;
    out.push({ id, summarySlot, flavor });
  }
  out.sort((a, b) => a.id.localeCompare(b.id));
  return out;
}

// Bottom-band geometry. Total content area is 1200 - 2×48 (face padding) =
// 1104u; minus the 28u inter-cell gap leaves 1076u to split between delight
// and pill cells. Default split 1.45:1 → delight ≈ 637u, pill ≈ 439u.
// Override moves the boundary in `pill_grow_u`-steps without touching the gap.
const BOTTOM_TOTAL = 1076;
const BOTTOM_GAP = 28;
const PILL_DEFAULT_W = 439;
const DELIGHT_PAD_RIGHT = 28;
// Per-form rules from summary.css (.summary-delight.text .body[data-form='X']).
// Used by the predictor to model overflow at each form's static size.
const DELIGHT_FORM_SIZE: Record<string, number> = {
  haiku: 36, tanka: 36, fragment: 36, aphorism: 36,
  quote: 34,
  sonnet: 28, 'free-verse': 28, stanzaic: 28, 'prose-poem': 28,
};
const DELIGHT_FORM_LH: Record<string, number> = {
  haiku: 52, tanka: 52, fragment: 48, aphorism: 48,
  quote: 46,
  sonnet: 40, 'free-verse': 40, stanzaic: 40, 'prose-poem': 40,
};
const STRICT_FORMS = new Set(['haiku', 'tanka', 'sonnet']);

export interface FaceTestParams {
  delightSize?: number;     // overrides per-form static (monolingual delight only)
  jaSize: number;
  enSize: number;
  pillSize: number;
  pillLineHeight: number;
  pillPad: boolean;
  pillGrowU: number;        // boundary shift (multiple of 30u in spirit, any int accepted)
}

interface DelightBilingualPredict {
  kind: 'bilingual';
  ja_max: number;
  en_max: number;
  width: number;
  budget: number;
  overflow: boolean;
  lineMismatch: boolean;
}
interface DelightMonoPredict {
  kind: 'monolingual';
  lines: number;
  max_chars: number;
  size: number;
  cap_rows: number;
  visual_rows: number;
  wrapped: boolean;
  overflow: boolean;
}
type DelightPredict = DelightBilingualPredict | DelightMonoPredict;

interface PillPredict {
  chars: number;
  charsPerLine: number;
  rows: number;
  capacity: number;
  overflow: boolean;
}

interface TripletPredict {
  triplet: Triplet;
  text?: CorpusText;
  pill?: PillPredict;
  delight?: DelightPredict;
  /** Either zone overflows. */
  anyOverflow: boolean;
}

function predictTripletFit(triplet: Triplet, text: CorpusText | undefined, p: FaceTestParams): TripletPredict {
  const out: TripletPredict = { triplet, anyOverflow: false };
  if (!text) return out;
  out.text = text;

  const pill_w = PILL_DEFAULT_W + p.pillGrowU;
  const delight_cell_w = BOTTOM_TOTAL - pill_w;
  const delight_body_w = delight_cell_w - DELIGHT_PAD_RIGHT;

  // ---- pill ----
  if (text.smart_pill_body) {
    const cpl = Math.floor(pill_w / (p.pillSize * PILL_CHAR_W));
    const usable_h = 408 - (p.pillPad ? 8 : 0);
    const rows = Math.round(usable_h / (p.pillSize * p.pillLineHeight));
    const capacity = Math.max(0, cpl) * Math.max(0, rows);
    const chars = text.smart_pill_body.length;
    out.pill = { chars, charsPerLine: cpl, rows, capacity, overflow: chars > capacity };
    if (out.pill.overflow) out.anyOverflow = true;
  }

  // ---- delight (every triplet, since the test page renders the summary-
  // slot text in delight regardless of flavor) ----
  const en = text.variants['en'];
  const ja = text.variants['ja'];
  if (!en || !text.form) return out;

  const isBilingualHaiku = !!ja && (text.form === 'haiku' || text.form === 'tanka');
  if (isBilingualHaiku) {
    const ja_lines = ja.split('\n').filter((l) => l.trim().length > 0);
    const en_lines = en.split('\n').filter((l) => l.trim().length > 0);
    const ja_max = ja_lines.reduce((m, l) => Math.max(m, [...l].length), 0);
    const en_max = en_lines.reduce((m, l) => Math.max(m, l.length), 0);
    const width = Math.round(ja_max * p.jaSize + 40 + en_max * p.enSize * 0.5);
    const lineMismatch = ja_lines.length !== en_lines.length;
    const overflow = width > delight_body_w || lineMismatch;
    out.delight = {
      kind: 'bilingual',
      ja_max, en_max, width,
      budget: delight_body_w,
      overflow, lineMismatch,
    };
    if (overflow) out.anyOverflow = true;
    return out;
  }

  // monolingual
  const en_lines = en.split('\n').filter((l) => l.trim().length > 0);
  const max_chars = en_lines.reduce((m, l) => Math.max(m, l.length), 0);
  const size = p.delightSize ?? DELIGHT_FORM_SIZE[text.form] ?? 28;
  const lh = DELIGHT_FORM_LH[text.form] ?? 40;
  const cpl = Math.max(1, Math.floor(delight_body_w / (size * 0.5)));
  let visual_rows = 0;
  let wrapped = false;
  for (const ln of en_lines) {
    const r = Math.max(1, Math.ceil(ln.length / cpl));
    if (r > 1) wrapped = true;
    visual_rows += r;
  }
  const cap_rows = Math.floor(408 / lh);
  const overflow =
    visual_rows > cap_rows ||
    (wrapped && STRICT_FORMS.has(text.form));
  out.delight = {
    kind: 'monolingual',
    lines: en_lines.length,
    max_chars,
    size,
    cap_rows,
    visual_rows,
    wrapped,
    overflow,
  };
  if (overflow) out.anyOverflow = true;
  return out;
}

/** Pareto frontier on a (x, y) where larger is "harder to fit" — i.e. a row
 *  is on the frontier iff no other row has both x' ≥ x and y' ≥ y with at
 *  least one strict. The `±margin` slack lets near-frontier entries through
 *  too, useful when the predictor has known calibration noise. */
function paretoFrontier<T>(rows: T[], xy: (r: T) => [number, number], margin = 0): T[] {
  return rows.filter((r) => {
    const [x, y] = xy(r);
    return !rows.some((q) => {
      if (q === r) return false;
      const [qx, qy] = xy(q);
      return qx >= x - margin && qy >= y - margin && (qx > x || qy > y);
    });
  });
}

/** Apply dominance filtering to the overflow set, returning only the
 *  triplets that aren't dominated by another in the same zone shape. The
 *  three shapes are independent (a bilingual delight overflow can't be
 *  dominated by a monolingual one), so we filter each bucket separately
 *  and union. */
export function dominanceFilter(rows: TripletPredict[], margin: number): TripletPredict[] {
  const overflowing = rows.filter((r) => r.anyOverflow);

  // Pill bucket: largest body length dominates; if it fits everyone fits.
  const pillOverflows = overflowing.filter((r) => r.pill?.overflow);
  const pillKeep = pillOverflows.length
    ? [pillOverflows.reduce((a, b) => ((a.pill!.chars >= b.pill!.chars) ? a : b))]
    : [];

  // Bilingual delight bucket: Pareto on (ja_max, en_max).
  const biOverflows = overflowing.filter(
    (r) => r.delight?.kind === 'bilingual' && r.delight.overflow,
  );
  const biKeep = paretoFrontier(
    biOverflows,
    (r) => {
      const d = r.delight as DelightBilingualPredict;
      return [d.ja_max, d.en_max];
    },
    margin,
  );

  // Monolingual delight bucket: Pareto on (lines, max_chars).
  const monoOverflows = overflowing.filter(
    (r) => r.delight?.kind === 'monolingual' && r.delight.overflow,
  );
  const monoKeep = paretoFrontier(
    monoOverflows,
    (r) => {
      const d = r.delight as DelightMonoPredict;
      return [d.lines, d.max_chars];
    },
    margin,
  );

  // Union (a triplet may be a dominator in one zone but not another;
  // pulling its triplet shows the user the worst case for that zone).
  const seen = new Set<string>();
  const out: TripletPredict[] = [];
  for (const r of [...pillKeep, ...biKeep, ...monoKeep]) {
    if (seen.has(r.triplet.id)) continue;
    seen.add(r.triplet.id);
    out.push(r);
  }
  return out;
}

export async function listFaceTriplets(): Promise<Triplet[]> {
  return listTriplets();
}

export async function predictAllTriplets(p: FaceTestParams): Promise<TripletPredict[]> {
  const triplets = await listTriplets();
  // Pre-load all referenced texts in one corpus walk; each triplet looks up
  // its summary slot in the index to avoid 1k file reads.
  const all = await listAllCorpusTexts();
  const byId = new Map(all.map((t) => [t.id, t]));
  return triplets.map((t) => predictTripletFit(t, byId.get(t.summarySlot), p));
}

// --- live render of one triplet (pair = real triplet's content) ----------

function injectFaceOverride(html: string, p: FaceTestParams): string {
  const pill_w = PILL_DEFAULT_W + p.pillGrowU;
  const delight_w = BOTTOM_TOTAL - pill_w;
  const padCss = p.pillPad
    ? ''
    : `
  .summary-smart-pill { justify-content: flex-start !important; }
  .summary-smart-pill .body { padding-bottom: 0 !important; }`;
  const delightSizeCss = p.delightSize
    ? `
  .summary-delight.text .body[data-form] { font-size: calc(${p.delightSize} * var(--u)) !important; }`
    : '';
  const css = `
<style data-debug="face-test">
  .summary-bottom {
    grid-template-columns: calc(${delight_w} * var(--u)) calc(${pill_w} * var(--u)) !important;
  }${delightSizeCss}
  .summary-delight.anthology .body .ja { font-size: calc(${p.jaSize} * var(--u)) !important; }
  .summary-delight.anthology .body .en { font-size: calc(${p.enSize} * var(--u)) !important; }
  .summary-smart-pill .body {
    font-size: calc(${p.pillSize} * var(--u)) !important;
    line-height: ${p.pillLineHeight} !important;
  }${padCss}
</style>
`;
  if (html.includes('</head>')) return html.replace('</head>', `${css}</head>`);
  return html.replace('<body>', `<body>${css}`);
}

async function gatherSummaryForTriplet(triplet: Triplet, text: CorpusText): Promise<unknown> {
  const weather = await requireInput('weather');
  const sonos = await loadInput('sonos');
  const device = await loadInput('device');
  const existingPairing = (await requireInput('pairing')) as Record<string, unknown>;
  const galleryAny = (existingPairing.gallery ?? {}) as Record<string, unknown>;

  const now = new Date();
  const tz = process.env.INKPLATE_RENDER_TZ || undefined;
  const time = new Intl.DateTimeFormat('en-GB', {
    hour: '2-digit', minute: '2-digit', hour12: false, timeZone: tz,
  }).format(now);
  const date = `${new Intl.DateTimeFormat('en-US', { weekday: 'long', timeZone: tz }).format(now)} · ${
    new Intl.DateTimeFormat('en-US', { month: 'long', day: 'numeric', timeZone: tz }).format(now)
  }`;

  // Pill body comes from the summary slot's text on every flavor.
  const pillBody = text.smart_pill_body ?? '';
  const smart_pill = { body: pillBody };

  // Delight: render the summary-slot text in every triplet (regardless of
  // flavor) so each card exercises both cells with real content. This
  // diverges from production for text-day (where the delight cell shows a
  // small image) — acceptable because the goal of the test page is to
  // spot-check delight + pill geometry against the actual text stored in
  // the triplet's `summary` slot.
  let companion: Record<string, unknown> | undefined;
  if (text.variants['en'] && text.form) {
    companion = {
      kind: 'text',
      form: text.form,
      body: text.variants['en'],
      poet: (text.author ?? '—').toString(),
      language: 'en',
    };
    if (text.variants['ja']) companion['body_ja'] = text.variants['ja'];
    if (text.title) companion['title'] = text.title;
    if (text.year) companion['dates'] = text.year;
  }
  // Build a fresh `gallery` block. Spreading `galleryAny` here was a bug:
  // for text-day triplets (where we intentionally leave `companion`
  // undefined so the delight cell shows the placeholder shell) the
  // existing pairing.json's companion would otherwise leak through, making
  // every text-day card render the operator's currently-published
  // companion instead of nothing. Only the gallery hero (`visual`) is
  // safe to inherit since it doesn't drive the Summary face anyway.
  const galleryBlock: Record<string, unknown> = { flavor: 'visual' };
  if (galleryAny['visual']) galleryBlock['visual'] = galleryAny['visual'];
  if (companion) galleryBlock['companion'] = companion;
  const pairing = {
    ...existingPairing,
    gallery: galleryBlock,
  };

  return { clock: { time, date }, weather, smart_pill, pairing, sonos, device };
}

export async function prepareFaceTest(triplet_id: string, p: FaceTestParams): Promise<ModePrepared> {
  const triplets = await listTriplets();
  const t = triplets.find((x) => x.id === triplet_id);
  if (!t) throw new Error(`triplet '${triplet_id}' not found`);
  const text = await loadCorpusText(t.summarySlot);
  const raw = await gatherSummaryForTriplet(t, text);
  const input = SCHEMAS.summary.parse(raw);
  const html = summary.buildHtml(input, 'a');
  const patched = injectFaceOverride(html, p);
  return { html: patched, dither: summary.ditherMask(input) };
}

export interface FaceTestPredictRow {
  triplet_id: string;
  summary_slot: string;
  flavor: 'visual-day' | 'text-day';
  pill?: PillPredict;
  delight?: DelightPredict;
}

export async function predictFaceTriplets(p: FaceTestParams): Promise<FaceTestPredictRow[]> {
  const rows = await predictAllTriplets(p);
  return rows.map((r) => {
    const out: FaceTestPredictRow = {
      triplet_id: r.triplet.id,
      summary_slot: r.triplet.summarySlot,
      flavor: r.triplet.flavor,
    };
    if (r.pill) out.pill = r.pill;
    if (r.delight) out.delight = r.delight;
    return out;
  });
}

export { type TripletPredict, type DelightPredict, type PillPredict };
