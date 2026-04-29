/**
 * Zone budget table.
 *
 * SOURCE OF TRUTH: `openspec/specs/dashboard-faces/spec.md` (Zone character
 * budgets requirement). Before archive, the same table lives at
 * `openspec/changes/add-dashboard-faces/specs/dashboard-faces/spec.md`.
 * `npm run check-zones` parses whichever exists.
 *
 * Every change to a budget edits the spec table FIRST, then this file.
 */

export type ZoneKind = 'prose' | 'verse';

export interface ZoneBudget {
  readonly maxChars: number;
  readonly maxLines: number;
  readonly kind: ZoneKind;
}

export const ZONES = {
  // ---- Summary ----------------------------------------------------------
  weather_cond:    { maxChars: 18, maxLines: 1, kind: 'prose' },
  forecast_cond:   { maxChars: 14, maxLines: 1, kind: 'prose' },
  news_body:       { maxChars: 50, maxLines: 14, kind: 'prose' },
  climate_label:   { maxChars: 12, maxLines: 1, kind: 'prose' },
  // The delight cell handles fit via metric-driven font ladder + CSS
  // `overflow: hidden` clip. The zone is now a wide prose backstop only
  // for catastrophic input (a whole prose chapter accidentally landing in
  // a delight slot). Whole short poems (~12 lines × ~40 chars = 500 chars)
  // must NOT be prose-truncated; the ladder shrinks them to fit instead.
  delight_text:    { maxChars: 80, maxLines: 16, kind: 'prose' },
  delight_attrib:  { maxChars: 40, maxLines: 1, kind: 'prose' },
  wx_nowcast:      { maxChars: 22, maxLines: 1, kind: 'prose' },

  // ---- Weather ----------------------------------------------------------
  location_name:   { maxChars: 16, maxLines: 1, kind: 'prose' },
  weather_cond_w:  { maxChars: 18, maxLines: 1, kind: 'prose' },
  astro_event:     { maxChars: 40, maxLines: 2, kind: 'prose' },
  astro_detail:    { maxChars: 26, maxLines: 2, kind: 'prose' },

  // ---- Gallery ----------------------------------------------------------
  /** Gallery-visual footer title — single row, full caption-band width, so
   *  long titles ("Rue de l'École de Médecine, Paris") render in one line.
   *  Attribution and clock sit on the row below (see gallery-visual.css). */
  gallery_title:        { maxChars: 56, maxLines: 1, kind: 'prose' },
  /** Gallery-text top-of-face title — generous, lets multi-word poem names
   *  ("Eu nu strivesc corola de minuni a lumii") render in full. */
  gallery_text_title:   { maxChars: 48, maxLines: 2, kind: 'prose' },
  gallery_attrib:  { maxChars: 32, maxLines: 1, kind: 'prose' },
  poem_body:       { maxChars: 64, maxLines: 32, kind: 'verse' },
  haiku_body:      { maxChars: 24, maxLines: 3,  kind: 'verse' },
  aphorism_body:   { maxChars: 48, maxLines: 6,  kind: 'verse' },
  quote_body:      { maxChars: 56, maxLines: 10, kind: 'verse' },

  // ---- Night ------------------------------------------------------------
  weekday_label:   { maxChars: 9,  maxLines: 1, kind: 'prose' },
  poetic_line:     { maxChars: 40, maxLines: 1, kind: 'prose' },
  hard_weather:    { maxChars: 16, maxLines: 1, kind: 'prose' },
  nocturne_attrib: { maxChars: 40, maxLines: 1, kind: 'prose' },

  // ---- Now-Playing ------------------------------------------------------
  np_title:        { maxChars: 24, maxLines: 2, kind: 'prose' },
  np_artist:       { maxChars: 28, maxLines: 1, kind: 'prose' },
  np_album:        { maxChars: 32, maxLines: 1, kind: 'prose' },
  np_source:       { maxChars: 20, maxLines: 1, kind: 'prose' },
  np_next:         { maxChars: 24, maxLines: 1, kind: 'prose' },
} as const satisfies Record<string, ZoneBudget>;

export type ZoneId = keyof typeof ZONES;

export function getZone(id: ZoneId): ZoneBudget {
  return ZONES[id];
}
