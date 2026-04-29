import type { DitherMask } from '../image/dither.js';
import {
  attributionLine,
  batteryIndicator,
  prettifyCondition,
  weatherIcon,
} from '../templateMacros.js';
import { applyZone } from '../zoneApply.js';
import { escapeHtml, htmlShell } from './shell.js';
import type { SummaryInput } from './schema.js';

/** Layout variant for the TOP-RIGHT weather quadrant.
 *  Pick via `?variant=a|b|c` on `/display/summary.png` (defaults to 'a').
 *    a = primary/secondary vertical stack (outside dominant)
 *    b = twin temperatures side-by-side (outside + inside equal weight)
 *    c = data grid (OUT/IN/H/L all at one scale)
 */
export type SummaryVariant = 'a' | 'b' | 'c';

export function buildHtml(input: SummaryInput, variant: SummaryVariant = 'a'): string {
  const loc = input.weather.locations[0]!;
  const next3 = loc.forecast.slice(0, 3);
  const todayHi = next3[0] ? Math.round(next3[0].high.c) : undefined;
  const todayLo = next3[0] ? Math.round(next3[0].low.c) : undefined;
  const outsideRaw = Math.round(loc.current.temp.c);
  const condition = applyZone('weather_cond', prettifyCondition(loc.current.condition));

  const forecastCells = next3
    .map((f) => `<div class="cell">
  <div class="left">
    <div class="day">${escapeHtml(f.day)}</div>
    <div class="cond">${escapeHtml(applyZone('forecast_cond', prettifyCondition(f.condition)))}</div>
  </div>
  <div class="middle">${weatherIcon(f.condition)}</div>
  <div class="right">
    <div class="hi">${Math.round(f.high.c)}&deg;</div>
    <div class="lo">${Math.round(f.low.c)}&deg;</div>
  </div>
</div>`)
    .join('');

  const delight = buildDelight(input);
  const smartPill = buildSmartPill(input, variant);

  const nowcastRaw = loc.nowcast?.label?.trim() || '';
  const nowcast = nowcastRaw ? applyZone('wx_nowcast', nowcastRaw) : '';

  const wxBlock = buildWxBlock(variant, {
    outside: outsideRaw,
    condition,
    hi: todayHi,
    lo: todayLo,
    nowcast,
  });

  const body = `
<div class="face mode summary-root" data-variant="${variant}">
  ${batteryIndicator(input.device?.battery?.percentage)}
  <section class="summary-top">
    <div class="clock-cell">
      <div class="date-line">${escapeHtml(input.clock.date)}</div>
      <div class="clock">${escapeHtml(input.clock.time)}</div>
    </div>
    <div class="vrule"></div>
    ${wxBlock}
  </section>
  <section class="summary-forecast">${forecastCells}</section>
  <section class="summary-bottom">
    ${delight}
    ${smartPill}
  </section>
</div>`;

  return htmlShell({
    title: 'Summary',
    styles: ['/static/css/summary.css'],
    body,
  });
}

interface WxFields {
  outside: number;
  condition: string;
  hi: number | undefined;
  lo: number | undefined;
  nowcast: string;
}

function buildWxBlock(variant: SummaryVariant, f: WxFields): string {
  const outStr = `${f.outside}&deg;`;
  const hiStr = f.hi !== undefined ? `${f.hi}&deg;` : '—';
  const loStr = f.lo !== undefined ? `${f.lo}&deg;` : '—';

  // Inside-climate was removed — no kitchen sensor will ship. Each variant now
  // shows only the outside block; the `variant` parameter is kept so a future
  // revision can reintroduce layouts without changing call sites.

  if (variant === 'b') {
    return `<div class="wx wx-b">
  <div class="outside-group">
    <div class="label">Outside</div>
    <div class="main">
      <div class="temp">${outStr}</div>
      <div class="meta">
        <div class="cond">${escapeHtml(f.condition)}</div>
        <div class="hl-stack">
          <div class="hl-row"><span class="hl-value">${hiStr}</span></div>
          <div class="hl-row"><span class="hl-value">${loStr}</span></div>
        </div>
      </div>
    </div>
  </div>
</div>`;
  }

  if (variant === 'c') {
    return `<div class="wx wx-c">
  <div class="outside-group">
    <div class="label">Outside</div>
    <div class="row">
      <div class="temp">${outStr}</div>
      <div class="meta">
        <div class="cond">${escapeHtml(f.condition)}</div>
        <div class="hl-row">
          <span class="hl"><span class="hl-value">${hiStr}</span></span>
          <span class="hl"><span class="hl-value">${loStr}</span></span>
        </div>
      </div>
    </div>
  </div>
</div>`;
  }

  // A (default) — condition icon (vertically centered, left column) + temp +
  // H/L stack. Per operator 2026-04-18: no "OUTSIDE" label, no condition
  // word; icon only. When the HA side publishes a short-term nowcast label
  // ("rain in ~2h", "clearing in 2h", "dry 6h+"), it renders in mono caps
  // underneath the icon, left-aligned. Absent → the line slot is empty.
  const nowcastMarkup = f.nowcast
    ? `<div class="nowcast">${escapeHtml(f.nowcast)}</div>`
    : '';
  return `<div class="wx wx-a">
  <div class="outside-group">
    <div class="icon-col">
      <div class="icon">${weatherIcon(f.condition)}</div>
      ${nowcastMarkup}
    </div>
    <div class="temp">${outStr}</div>
    <div class="hl-stack">
      <div class="hl-row"><span class="hl-value">${hiStr}</span></div>
      <div class="hl-row"><span class="hl-value">${loStr}</span></div>
    </div>
  </div>
</div>`;
}

/** Pick a font-size tier for the delight body cell. Each tier is defined
 * by a (font, line-height, max-cpl, max-lines) tuple — `cpl` is what fits
 * one visual line in the ~552u cell at that font, `max-lines` is what
 * fits the ~440u height at that line-height. We pick the LARGEST tier
 * where every author line fits in 1 visual line AND the total line count
 * fits the cell — so the poet's chosen breaks render as written, never
 * mid-clause wrapping.
 *
 * Floor preference: 28u (parity with the pill, which is 28u/lh 1.1). The
 * cell wins on hierarchy when content allows. We drop below 28u only
 * when no higher tier fits the content without ugly wrap (long German
 * lines, Whitman, Eliot pentameter — Rilke "Der Panther" has 47-char
 * lines that need 24u to live on one row each). */
/** Tier: (tier, font, line-height, soft-cpl, max-visual-lines).
 * Tiers 1-5 are pill-parity (≥28u). Tiers 6-7 drop below the pill and
 * are the unwrapped-escape last-resort — only used when neither
 * unwrapped at ≥28u NOR wrapped at 28u fits the cell.
 *
 * Body cell vertical budget: ~380u (panel height 825u − top section ~220u
 * − forecast 130u − padding-bottom 18u − padding-top 20u − attribution
 * 36u − attribution-gap 10u). max-visual-lines = floor(380/lh) with one
 * line of margin to avoid edge clip. */
// soft-cpl values calibrated against IBM Plex Serif at 552u cell width
// (≈0.42× font width per char for English mixed case in this typeface).
const DELIGHT_TIERS = [
  // [tier, font, line-height, soft-cpl, max-visual-lines]
  [1, 36, 48, 34,  7],
  [2, 32, 44, 38,  8],
  [3, 30, 40, 41,  9],
  [4, 28, 34, 44, 11],
  [5, 28, 30, 44, 12],
  [6, 24, 32, 52, 11],
  [7, 22, 28, 57, 13],
] as const;
const PILL_FLOOR_TIERS = [1, 2, 3, 4, 5];   // ≥28u
const WRAP_TIERS_AT_FLOOR = [4, 5];          // 28u tiers used in Phase 2
const SUB_FLOOR_TIERS = [6, 7];               // <28u escape (Phase 3)

/** Estimate the number of visual lines a body will occupy at a given
 * cpl budget — each author line wraps to ⌈len / cpl⌉ visual lines. */
function visualLinesAt(authorLines: string[], cpl: number): number {
  let total = 0;
  for (const ln of authorLines) {
    total += Math.max(1, Math.ceil(ln.length / cpl));
  }
  return total;
}

function pickFitTier(body: string): number {
  const lines = body.split(/\r?\n/).map(s => s.trimEnd()).filter(s => s.length > 0);
  const n = lines.length;
  const longest = lines.reduce((m, ln) => Math.max(m, ln.length), 0);
  const tierCfg = (t: number) => DELIGHT_TIERS.find(x => x[0] === t)!;

  // Phase 1 — prefer largest unwrapped at ≥28u.
  for (const t of PILL_FLOOR_TIERS) {
    const [, , , cpl, mvl] = tierCfg(t);
    if (longest <= cpl && n <= mvl) return t;
  }
  // Phase 2 — wrap at 28u. Tier 4 first (more line-height room),
  // fall back to tier 5 (tighter lh) when tier 4's vertical budget is
  // exceeded. Larger fonts (tiers 1-3) with wrap are deliberately NOT
  // considered: the same wrap looks heavier the larger the font.
  for (const t of WRAP_TIERS_AT_FLOOR) {
    const [, , , cpl, mvl] = tierCfg(t);
    if (visualLinesAt(lines, cpl) <= mvl) return t;
  }
  // Phase 3 — below-pill unwrapped escape. Used only when 28u-with-wrap
  // overflows vertically (very rare for summary-eligible items, since
  // those are gated to ≤5 author lines).
  for (const t of SUB_FLOOR_TIERS) {
    const [, , , cpl, mvl] = tierCfg(t);
    if (longest <= cpl && n <= mvl) return t;
  }
  // Last resort — accept wrap below pill at the smallest tier.
  return 7;
}

/** True when any author line at the chosen tier's cpl will wrap to ≥2
 * visual lines. Used to switch alignment from centered to left+turnover. */
function delightWillWrap(body: string, tier: number): boolean {
  const t = DELIGHT_TIERS.find(t => t[0] === tier);
  if (!t) return false;
  const softCpl = t[3];
  const lines = body.split(/\r?\n/).map(s => s.trimEnd()).filter(s => s.length > 0);
  return lines.some(ln => ln.length > softCpl);
}

function buildDelight(input: SummaryInput): string {
  const g = input.pairing.gallery;
  const c = g.companion;
  // Visual-day hero (image on Gallery) → delight renders companion TEXT.
  // Text-day hero (text on Gallery) → delight renders a small IMAGE with caption.
  if (!c) {
    const shell = g.flavor === 'visual' ? 'text' : 'image';
    return `<section class="summary-delight ${shell}"><div class="body placeholder-dash"></div><div class="attrib">—</div></section>`;
  }
  if (c.kind === 'text') {
    const attrib = c.poet
      ? attributionLine(c.poet.toUpperCase(), c.dates)
      : '—';
    // Anthology side-by-side: haiku/tanka with body_ja renders Japanese
    // original on the left and the translation in italic on the right.
    const hasAnthology =
      (c.form === 'haiku' || c.form === 'tanka') && !!c.body_ja && c.body_ja.trim().length > 0;
    if (hasAnthology) {
      const jaLines = c.body_ja!.replace(/^(?:\r?\n)+|(?:\r?\n)+$/g, '');
      return `<section class="summary-delight text anthology" data-form="${escapeHtml(c.form)}">
  <div class="body">
    <div class="ja" lang="ja">${escapeHtml(jaLines)}</div>
    <div class="en">${escapeHtml(applyZone('delight_text', c.body))}</div>
  </div>
  <div class="attrib">${escapeHtml(applyZone('delight_attrib', attrib))}</div>
</section>`;
    }
    const tier = pickFitTier(c.body);
    const wraps = delightWillWrap(c.body, tier);
    // Each author line in its own <div class="line"> so CSS can apply the
    // hanging-indent rule (text-indent: -2em; padding-left: 2em) — first
    // visual sub-line stays at column 0; any wrap continuation indents
    // by 2em so the reader reads the indent as "this is a wrap, not a
    // new poetic line." Center alignment is incompatible with the
    // turnover; switch to left+turnover when wrap is detected.
    const cookedBody = applyZone('delight_text', c.body);
    const lineDivs = cookedBody
      .split(/\r?\n/)
      .map(s => s.trim())
      .filter(s => s.length > 0)
      .map(s => `<div class="line">${escapeHtml(s)}</div>`)
      .join('\n');
    const wrapClass = wraps ? ' wrap-turnover' : '';
    return `<section class="summary-delight text${wrapClass}" data-form="${escapeHtml(c.form)}" data-fit-tier="${tier}">
  <div class="body" data-form="${escapeHtml(c.form)}" data-fit-tier="${tier}">${lineDivs}</div>
  <div class="attrib">${escapeHtml(applyZone('delight_attrib', attrib))}</div>
</section>`;
  }
  // c.kind === 'visual': small image + mono-caps caption.
  const attrib = attributionLine(c.artist.toUpperCase(), c.year);
  const caption = c.title ? `${c.title} · ${attrib}` : attrib;
  return `<section class="summary-delight image">
  <div class="body"><img src="${escapeHtml(c.image_path)}" alt=""></div>
  <div class="attrib">${escapeHtml(applyZone('delight_attrib', caption))}</div>
</section>`;
}

/** Convert markdown-style `*word*` to bolded inline content, after HTML
 *  escaping. Asterisks are not HTML-special so they survive escapeHtml,
 *  letting us run the regex on the escaped string. */
function boldHeadword(escaped: string): string {
  return escaped.replace(/\*([^*\n]+)\*/g, '<strong>$1</strong>');
}

function buildSmartPill(input: SummaryInput, _variant: SummaryVariant): string {
  // Smart pill — lower-right zone of the Summary face. A single deep-dive
  // entry (word-of-day or concept-of-day) bound to the companion on the left.
  // Font size + line-height are fixed in `summary.css` (28u / 1.1 in the
  // post-shift 499u cell) — capacity 35cpl × 13r = 455 chars. The earlier
  // step-down ladder (36u → 21u) was removed when calibration validated
  // that 28u accommodates every authored pill body in the corpus without
  // dropping below the 25u readability floor. Bodies authored above 455
  // chars overflow visibly so the operator catches them at ingestion.
  const first = input.news.items[0];
  if (!first) {
    return `<section class="summary-smart-pill">
  <div class="news"><div class="item"><div class="body placeholder-dash"></div></div></div>
</section>`;
  }
  const safe = applyZone('news_body', first.body);
  const bodyHtml = boldHeadword(escapeHtml(safe));
  return `<section class="summary-smart-pill">
  <div class="news"><div class="item"><div class="body">${bodyHtml}</div></div></div>
</section>`;
}

export function ditherMask(input: SummaryInput): boolean | DitherMask {
  const g = input.pairing.gallery;
  const hasImage = g.flavor === 'text';
  if (!hasImage) return false;
  const W = 1200;
  const H = 825;
  const x0 = 48;
  const y0 = 500;
  const x1 = 650;
  const y1 = 770;
  const data = new Uint8Array(W * H);
  for (let y = y0; y < y1; y++) {
    for (let x = x0; x < x1; x++) data[y * W + x] = 1;
  }
  return { width: W, height: H, data };
}
