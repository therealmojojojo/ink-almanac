import {
  batteryIndicator,
  moonGlyph,
  prettifyCondition,
  svgGlyph,
  weatherIcon,
} from '../templateMacros.js';
import { applyZone } from '../zoneApply.js';
import { escapeHtml, htmlShell } from './shell.js';
import type { WeatherModeInput } from './schema.js';

/**
 * Weather face — header + two location rows + astro footer.
 */
export function buildHtml(input: WeatherModeInput): string {
  const locations = input.weather.locations;
  while (locations.length < 2) {
    locations.push({
      name: '',
      current: { condition: '', temp: { c: NaN } },
      forecast: [],
    } as (typeof locations)[number]);
  }

  const rows = locations
    .slice(0, 2)
    .map((loc) => renderRow(loc))
    .join('');

  const astro = input.weather.astro;
  const sunRise = astro?.sun?.rise ?? astro?.event?.when?.split('/')[0]?.trim();
  const sunSet = astro?.sun?.set ?? astro?.event?.when?.split('/')[1]?.trim();

  const body = `
<div class="face mode weather-root">
  ${batteryIndicator(input.device?.battery?.percentage)}
  <header class="weather-header">
    <span class="title">Weather</span>
    <span class="date">${escapeHtml(input.clock.date)}</span>
    <span class="clock">${escapeHtml(input.clock.time)}</span>
  </header>
  ${rows}
  <footer class="weather-astro">
    <div class="cell">
      <div class="label">Sun</div>
      <div class="sun-times">
        <div class="sun-row">${svgGlyph('icon-sunrise', 'sicon')}<span>${escapeHtml(sunRise ?? '—')}</span></div>
        <div class="sun-row">${svgGlyph('icon-sunset', 'sicon')}<span>${escapeHtml(sunSet ?? '—')}</span></div>
      </div>
    </div>
    <div class="cell">
      <div class="label">Moon</div>
      <div class="moon-block">
        ${astro?.moon ? moonGlyph(astro.moon.phase) : moonGlyph('full')}
        <span class="phase">${escapeHtml(
          astro?.moon?.phase?.toUpperCase() ?? '—',
        )}</span>
      </div>
    </div>
    <div class="cell">
      <div class="label">Stars</div>
      ${(() => {
        const text = applyZone('astro_event', astro?.event?.title ?? 'no event tonight');
        const tier = pickStarsTier(text);
        return `<div class="value" data-fit-tier="${tier}">${escapeHtml(text)}</div>`;
      })()}
    </div>
  </footer>
</div>`;

  return htmlShell({ title: 'Weather', styles: ['/static/css/weather.css'], body });
}

function renderRow(loc: WeatherModeInput['weather']['locations'][number]): string {
  if (!loc.name) {
    return `<section class="weather-row">
      <div class="name-block"><span class="name placeholder-dash"></span></div>
      <div class="current placeholder-dash"></div>
      <div class="forecast"></div>
    </section>`;
  }
  const forecast = loc.forecast
    .slice(0, 5)
    .map(
      (f) => `<div class="cell">
  <div class="day">${escapeHtml(f.day.toUpperCase())}</div>
  ${weatherIcon(f.condition)}
  <div class="hi">${Math.round(f.high.c)}&deg;</div>
  <div class="lo">${Math.round(f.low.c)}&deg;</div>
</div>`,
    )
    .join('');

  const tempNum = Number.isFinite(loc.current.temp.c)
    ? `${Math.round(loc.current.temp.c)}&deg;`
    : '—';
  const hi = loc.forecast[0] ? Math.round(loc.forecast[0].high.c) : undefined;
  const lo = loc.forecast[0] ? Math.round(loc.forecast[0].low.c) : undefined;

  const condText = loc.current.condition
    ? prettifyCondition(loc.current.condition)
    : '—';

  // Short-horizon precipitation nowcast inlined on the same line as the
  // condition word ("cloudy, dry 6h+", "partly cloudy, rain in 8 min").
  // Each piece is zone-budgeted independently so neither truncates the
  // other; the comma-join happens post-zone. Label source: HA side, OWM
  // OneCall minutely with MET.no hourly as fallback.
  const nowcastText = loc.nowcast?.label?.trim() ?? '';
  const condPart = applyZone('weather_cond_w', condText);
  const nowcastPart = nowcastText
    ? applyZone('wx_nowcast', nowcastText).toLowerCase()
    : '';
  const condLine = nowcastPart ? `${condPart}, ${nowcastPart}` : condPart;

  return `<section class="weather-row">
  <div class="name-block">
    <div class="name">${escapeHtml(
      applyZone('location_name', loc.name).toUpperCase(),
    )}</div>
  </div>
  <div class="current">
    <div class="top">
      <div class="temp">${tempNum}</div>
      <div class="hl-stack">
        <div class="hl-row"><span class="hl-value">${
          hi !== undefined ? `${hi}°` : '—'
        }</span></div>
        <div class="hl-row"><span class="hl-value">${
          lo !== undefined ? `${lo}°` : '—'
        }</span></div>
      </div>
    </div>
    <div class="cond">${escapeHtml(condLine)}</div>
  </div>
  <div class="forecast">${forecast}</div>
</section>`;
}

/** Tiered font-fit for the Stars cell single statement. The cell is one
 *  third of the panel width (≈360u inner) and sits in a fixed-footprint
 *  footer; the picker keeps total text height under today's max envelope.
 *
 *  [tier, font(u), line-height(u), soft-cpl, max-visual-lines]
 *
 *  Soft-cpl is calibrated for IBM Plex Sans 500 at ~0.51× font advance per
 *  char on English mixed-case prose. May need tuning after first renders.
 *  max-visual-lines is set so each tier's content height stays inside the
 *  cell budget (≤ ~108u of value text). Larger fonts are capped at 2 lines
 *  to preserve hierarchy with the Sun and Moon cells; floor tiers (≤25u)
 *  may run to 3 lines on long statements (Phase 2). */
const STARS_TIERS = [
  // [tier, font, line-height, soft-cpl, max-visual-lines]
  [1, 30, 36, 23, 2],
  [2, 28, 34, 25, 2],
  [3, 27, 32, 26, 2],
  [4, 26, 32, 27, 2],
  [5, 25, 30, 28, 3],
  [6, 22, 28, 32, 3],
  [7, 20, 26, 35, 3],
] as const;

function pickStarsTier(text: string): number {
  const len = text.length || 1;
  // Phase 1 — largest tier ≥ 25u (the Moon-cell floor) where the statement
  // fits on a single line. Prevents shrinking past the footer floor just
  // to avoid wrap; on chatty content we prefer 30u wrapped over 20u single.
  for (const [t, font, , cpl] of STARS_TIERS) {
    if (font >= 25 && len <= cpl) return t;
  }
  // Phase 2 — largest tier where wrapped lines fit the tier's mvl. This
  // is where 30u-with-2-lines beats 22u-with-1-line for medium statements.
  for (const [t, , , cpl, mvl] of STARS_TIERS) {
    if (Math.ceil(len / cpl) <= mvl) return t;
  }
  // Last resort — floor; CSS overflow trims if text really runs away.
  return 7;
}

export function ditherMask(): boolean {
  return false;
}
