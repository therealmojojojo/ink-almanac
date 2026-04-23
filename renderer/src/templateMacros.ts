import { escapeHtml } from './modes/shell.js';

/**
 * Shared render helpers used across faces. See `renderer/docs/faces.md` for
 * the zone glossary and the delight-zone flavor rule.
 */

export function attributionLine(name: string, dates?: string, medium?: string): string {
  const parts = [name];
  if (medium) parts.push(medium);
  if (dates) parts.push(dates);
  return parts.join(' · ');
}

/** Battery indicator HTML, placed inside the mode root (position: absolute). */
export function batteryIndicator(percentage: number | undefined): string {
  const safe = typeof percentage === 'number' ? Math.max(0, Math.min(100, Math.round(percentage))) : undefined;
  const label = safe === undefined ? '—' : `${safe}%`;
  const fillPct = safe ?? 100;
  return `<div class="battery-indicator">
  <span class="glyph"><span class="fill" style="width:${fillPct}%"></span></span>
  <span>${escapeHtml(label)}</span>
</div>`;
}

/** Human-readable form of an HA `weather.*` condition slug (e.g. `partlycloudy` → `partly cloudy`). */
export function prettifyCondition(condition: string): string {
  const s = condition.trim().toLowerCase();
  const map: Record<string, string> = {
    'clear-night': 'clear',
    'cloudy': 'cloudy',
    'exceptional': 'exceptional',
    'fog': 'fog',
    'hail': 'hail',
    'lightning': 'lightning',
    'lightning-rainy': 'thunderstorms',
    'partlycloudy': 'partly cloudy',
    'pouring': 'pouring',
    'rainy': 'rain',
    'snowy': 'snow',
    'snowy-rainy': 'sleet',
    'sunny': 'sunny',
    'windy': 'windy',
    'windy-variant': 'windy',
  };
  if (map[s]) return map[s];
  return s.replace(/[-_]+/g, ' ');
}

/** Weather icon `<svg>` keyed by condition string. */
export function weatherIcon(condition: string): string {
  const id = conditionToIcon(condition);
  return `<svg class="wicon" width="48" height="48" aria-hidden="true"><use href="#${id}"/></svg>`;
}

function conditionToIcon(c: string): string {
  const s = c.toLowerCase();
  if (s.includes('snow')) return 'icon-snow';
  if (s.includes('rain') || s.includes('drizzle') || s.includes('shower')) return 'icon-rain';
  if (s.includes('overcast')) return 'icon-overcast';
  if (s.includes('partly') || s.includes('partly cloudy')) return 'icon-partly-cloudy';
  if (s.includes('cloud')) return 'icon-cloud';
  if (s.includes('clear') || s.includes('sun')) return 'icon-sun';
  return 'icon-partly-cloudy';
}

/** Generic SVG glyph reference by id. */
export function svgGlyph(id: string, cls = 'glyph'): string {
  return `<svg class="${cls}" width="48" height="48" aria-hidden="true"><use href="#${id}"/></svg>`;
}

/** Moon-phase `<svg>` keyed by phase slug. */
export function moonGlyph(phase: string): string {
  const id = phaseToId(phase);
  return `<svg class="moon" width="48" height="48" aria-hidden="true"><use href="#${id}"/></svg>`;
}

function phaseToId(p: string): string {
  const s = p.toLowerCase().replace(/\s+/g, '-');
  const map: Record<string, string> = {
    'new': 'moon-new',
    'waxing-crescent': 'moon-waxing-crescent',
    'first-quarter': 'moon-first-quarter',
    'waxing-gibbous': 'moon-waxing-gibbous',
    'full': 'moon-full',
    'waning-gibbous': 'moon-waning-gibbous',
    'last-quarter': 'moon-last-quarter',
    'waning-crescent': 'moon-waning-crescent',
  };
  return map[s] ?? 'moon-full';
}

/** Em-dash placeholder for null/missing prose fields. */
export const EM_DASH = '—';
export function orDash(v: string | undefined | null): string {
  return v ? v : EM_DASH;
}

/** Weekday label (UTC-based; consumers may swap to locale-aware later). */
export function weekdayLabel(isoDate: string): string {
  const t = Date.parse(isoDate);
  if (Number.isNaN(t)) return EM_DASH;
  const day = new Date(t).toUTCString().slice(0, 3); // Sun, Mon, ...
  const map: Record<string, string> = {
    Sun: 'SUNDAY', Mon: 'MONDAY', Tue: 'TUESDAY',
    Wed: 'WEDNESDAY', Thu: 'THURSDAY', Fri: 'FRIDAY', Sat: 'SATURDAY',
  };
  return map[day] ?? EM_DASH;
}
