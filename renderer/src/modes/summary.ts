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
  const sidebar = buildSidebar(input, variant);

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
    ${sidebar}
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
    return `<section class="summary-delight text" data-form="${escapeHtml(c.form)}">
  <div class="body" data-form="${escapeHtml(c.form)}">${escapeHtml(applyZone('delight_text', c.body))}</div>
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

function buildSidebar(input: SummaryInput, _variant: SummaryVariant): string {
  // Sidebar no longer varies by variant. Three HN items with dashed separators.
  const hn = input.hn.items;
  const hnItem = (it: { title: string; subtitle?: string | undefined }) =>
    `<div class="item">
  <div class="title">${escapeHtml(applyZone('hn_title', it.title))}</div>
  ${
    it.subtitle
      ? `<div class="subtitle">${escapeHtml(applyZone('hn_subtitle', it.subtitle))}</div>`
      : ''
  }
</div>`;
  const items = hn.slice(0, 3).map(hnItem).join('') ||
    `<div class="item"><div class="title placeholder-dash"></div></div>`;
  return `<section class="summary-sidebar">
  <div class="label">Reading today</div>
  <div class="hn">${items}</div>
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
