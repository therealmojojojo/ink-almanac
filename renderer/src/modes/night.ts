import type { DitherMask } from '../image/dither.js';
import { weekdayLabel } from '../templateMacros.js';
import { applyZone } from '../zoneApply.js';
import { escapeHtml, htmlShell } from './shell.js';
import type { NightInput } from './schema.js';

/**
 * Approximate-time phrase for the Night face. Shared algorithm with the
 * firmware's local-tick renderer (see `add-local-clock-tick` spec "Local-tick
 * rendering"). Renderer and firmware MUST agree on this function; divergence
 * is a spec violation.
 */
const HOUR_WORDS = [
  'twelve', 'one', 'two', 'three', 'four', 'five',
  'six', 'seven', 'eight', 'nine', 'ten', 'eleven',
];

function wordForHour12(h12: number): string {
  // h12 ∈ 1..12
  return HOUR_WORDS[h12 % 12] ?? 'twelve';
}

export function nightPhrase(h: number, m: number): string {
  const hour12 = ((h + 11) % 12) + 1;       // 1..12
  const nextHour12 = (hour12 % 12) + 1;
  if (m <= 14) return `${wordForHour12(hour12)} o'clock`;
  if (m <= 29) return `quarter past ${wordForHour12(hour12)}`;
  if (m <= 44) return `half past ${wordForHour12(hour12)}`;
  return `quarter to ${wordForHour12(nextHour12)}`;
}

/** Compress wordy condition strings so the hard_weather line fits its 16-char budget. */
function compactCondition(c: string): string {
  const s = c.toLowerCase();
  // "partly cloudy" simplifies to "cloudy" at night — "partly" alone is
  // meaningless and the full string overflows the 16-char hard_weather budget.
  if (s.includes('partly')) return 'cloudy';
  if (s.includes('overcast')) return 'overcast';
  if (s.includes('cloud')) return 'cloudy';
  if (s.includes('rain') || s.includes('drizzle') || s.includes('shower')) return 'rain';
  if (s.includes('snow')) return 'snow';
  if (s.includes('clear') || s.includes('sun')) return 'clear';
  if (s.includes('fog') || s.includes('mist')) return 'fog';
  return c.length <= 8 ? c : c.slice(0, 7);
}

export function buildHtml(input: NightInput): string {
  const [hh, mm] = input.clock.time.split(':');
  const phrase = nightPhrase(Number(hh) || 0, Number(mm) || 0);
  const loc = input.weather.locations[0];
  const temp = loc && Number.isFinite(loc.current.temp.c) ? Math.round(loc.current.temp.c) : '—';
  const compactCond = compactCondition(loc?.current.condition ?? 'calm');
  const hardText = `${temp}° · ${compactCond.toUpperCase()}`;
  const poetic = input.weather.poetic
    ? applyZone('poetic_line', input.weather.poetic)
    : '';
  const nocturne = input.pairing.night?.image_path;
  const title = input.pairing.night?.title ?? '';
  const fragment = input.pairing.night?.fragment;

  const weekday = applyZone('weekday_label', weekdayLabel(input.pairing.date));

  // Caption size bucket — shorter titles get extra top-padding so the
  // caption block's top edge doesn't float midway up the column.
  // - none:   no title and no attribution → caption is omitted
  // - short:  ≤ 28 chars (unlikely to wrap) → extra slack above
  // - medium: 29–48 chars (one full line)  → small slack
  // - long:   > 48 chars (wraps to 2 lines) → no slack
  let captionSize: 'short' | 'medium' | 'long' = 'long';
  const titleLen = title.length;
  if (titleLen <= 28) captionSize = 'short';
  else if (titleLen <= 48) captionSize = 'medium';

  const caption = (title || fragment)
    ? `<div class="night-caption" data-size="${captionSize}">
      ${title ? `<div class="title">${escapeHtml(applyZone('gallery_title', title))}</div>` : ''}
      ${fragment ? `<div class="attrib">${escapeHtml(applyZone('nocturne_attrib', fragment))}</div>` : ''}
    </div>`
    : '';

  // When there's no nocturne image, collapse to a single-column layout and
  // leave the caption in the left column so the face is never empty.
  const body = nocturne
    ? `
<div class="face night-root with-image">
  <section class="night-left">
    <div class="night-top">
      <div class="night-phrase">${escapeHtml(phrase)}</div>
      <div class="night-weekday">${escapeHtml(weekday)}</div>
      ${poetic ? `<div class="night-poetic">${escapeHtml(poetic)}</div>` : ''}
      <div class="night-hard">${escapeHtml(applyZone('hard_weather', hardText))}</div>
    </div>
    ${caption}
  </section>
  <section class="night-nocturne">
    <img src="${escapeHtml(nocturne)}" alt="">
  </section>
</div>`
    : `
<div class="face night-root no-image">
  <section class="night-left">
    <div class="night-top">
      <div class="night-phrase">${escapeHtml(phrase)}</div>
      <div class="night-weekday">${escapeHtml(weekday)}</div>
      ${poetic ? `<div class="night-poetic">${escapeHtml(poetic)}</div>` : ''}
      <div class="night-hard">${escapeHtml(applyZone('hard_weather', hardText))}</div>
    </div>
    ${caption}
  </section>
</div>`;

  return htmlShell({ title: 'Night', styles: ['/static/css/night.css'], body });
}

export function ditherMask(input: NightInput): boolean | DitherMask {
  if (!input.pairing.night?.image_path) return false;
  const W = 1200;
  const H = 825;
  const data = new Uint8Array(W * H);
  // Nocturne column is the right ~1.3/2.3 share of the content area, so
  // roughly x ∈ [576, 1152]; plus padding reach to full-height.
  const x0 = 576;
  const x1 = 1200;
  const y0 = 0;
  const y1 = H;
  for (let y = y0; y < y1; y++) {
    for (let x = x0; x < x1; x++) data[y * W + x] = 1;
  }
  return { width: W, height: H, data };
}
