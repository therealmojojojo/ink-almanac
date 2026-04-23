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
      <div class="label">Tonight</div>
      <div class="value">${escapeHtml(
        applyZone('astro_event', astro?.event?.title ?? 'no event tonight'),
      )}</div>
      ${
        astro?.event?.detail
          ? `<div class="detail">${escapeHtml(
              applyZone('astro_detail', astro.event.detail),
            )}</div>`
          : ''
      }
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
    <div class="cond">${escapeHtml(applyZone('weather_cond_w', condText))}</div>
  </div>
  <div class="forecast">${forecast}</div>
</section>`;
}

export function ditherMask(): boolean {
  return false;
}
