/**
 * Form-driven typography routing.
 *
 * EXPERIMENTAL (2026-04-14): all forms render in Fraunces Regular, left-
 * aligned. Multi-column layout kicks in when content exceeds the
 * per-column line budget. This replaces the earlier italic/centered
 * treatments for haiku/tanka/fragment/aphorism — the spec's
 * "Ozymandias in italics" rule generalizes to "nothing in italics."
 *
 * If this experiment sticks, `openspec/specs/dashboard-faces/spec.md`
 * and `specs/typography-routing/spec.md` both need amending.
 */

export type Form =
  | 'haiku'
  | 'tanka'
  | 'sonnet'
  | 'free-verse'
  | 'stanzaic'
  | 'fragment'
  | 'aphorism'
  | 'prose-poem'
  | 'quote';

export interface TypographyRule {
  readonly family: 'Fraunces';
  readonly style: 'regular';
  readonly opsz: number;
  readonly size: number; // in `u` units
  readonly align: 'left';
  readonly hangingIndent: boolean;
  readonly openingEmDash: boolean;
  readonly attributionItalic: boolean;
}

/** Hard per-column line budget. Content flows into additional columns beyond this. */
export const MAX_LINES_PER_COLUMN = 8;

/** Hard per-column character width budget (used to decide column count for prose-poem). */
export const MAX_CHARS_PER_COLUMN = 48;

/** Default rule — all forms share this now. Size is still per-form. */
const BASE: Omit<TypographyRule, 'size'> = {
  family: 'Fraunces',
  style: 'regular',
  opsz: 72,
  align: 'left',
  hangingIndent: true,
  openingEmDash: false,
  attributionItalic: false,
};

export const FORMS: Record<Form, TypographyRule> = {
  haiku:         { ...BASE, size: 42 },
  tanka:         { ...BASE, size: 42 },
  sonnet:        { ...BASE, size: 42 },
  'free-verse':  { ...BASE, size: 42 },
  stanzaic:      { ...BASE, size: 42 },
  fragment:      { ...BASE, size: 48 },
  aphorism:      { ...BASE, size: 52 },
  'prose-poem':  { ...BASE, size: 36 },
  quote:         { ...BASE, size: 44 },
};

export function typographyFor(form: Form): TypographyRule {
  return FORMS[form];
}

/**
 * Decide how many columns to flow the body into. Rule: max 8 lines per column.
 * A 4-stanza poem flows 2 stanzas per column when column count is 2, so long
 * as stanzas are kept together (`break-inside: avoid` on .stanza).
 */
export function columnCount(totalLines: number): number {
  if (totalLines <= MAX_LINES_PER_COLUMN) return 1;
  return 2;
  // 3-column layout at panel-native width (960u content block) gives only
  // ~272u per column, too tight for most verse. We accept that very long
  // poems (18+ lines) will overflow vertically at 2 cols and signal the
  // operator via visible overflow rather than try to cram 3 cols.
}

/**
 * Content-aware fit for the gallery-text face.
 *
 * Given the body lines and the form's base size, picks (cols, fontSizeU) so
 * that:
 *   - the widest line fits inside a single column at the chosen size (no
 *     mid-line visual wrap), AND
 *   - the stacked line count fits the available face height.
 *
 * Shrinks the font in 2u steps down to `MIN_FONT_U` when the base size can't
 * absorb the content. Catches long-line poems (multi-stanza stanzaic
 * fragments, Arghezi-length testaments, etc.) where the per-form base size
 * alone would overflow.
 *
 * Constants are empirical for Fraunces Regular at the ops/wght we ship. The
 * function is a heuristic, not a layout engine — it optimises for "no visible
 * overflow on common long-form content" without running Playwright twice.
 */
const CONTENT_WIDTH_U = 1056;       // .gt-content max-width in u (1200 face − 2×72u side padding)
const COLUMN_GAP_U = 72;             // CSS column-gap
const AVG_CHAR_WIDTH_FACTOR = 0.50;  // Fraunces Regular empirical char-width / font-size. Raised from 0.46 after observing 59-char lines soft-wrap at what the fit calc said should fit — the 0.46 was measured on light-letter samples and underestimated real lines with many normal-width letters.
const LINE_HEIGHT_FACTOR = 1.30;

// Face geometry — must stay in sync with gallery-text.css. The fit pass
// computes the body's vertical budget from these primitives rather than
// a flat constant, so it can respect:
//   - stanza margin overhead (scales with body size and stanza count),
//   - minimum clearance above the attribution (prevents the last verse
//     from landing on the author line — user-stated constraint).
const FACE_HEIGHT_U = 825;
const TOP_PAD_U = 48;              // .gt-root padding-top
const ATTRIB_BOTTOM_U = 36;        // .gt-attrib bottom offset
const ATTRIB_HEIGHT_U = 25;        // mono 25u × line-height 1.0
const STANZA_MARGIN_FACTOR = 1.0;  // CSS stanza margin = bodyLeading × this (1.0 = one blank line)
const TITLE_BODY_GAP_FACTOR = 0.8; // title→body gap = bodyLeading × this (tighter than a full leading — saves vertical budget for long forms)
const ABOVE_ATTRIB_CLEARANCE = 1.2; // default min gap above attribution = bodyLeading × this (>1 per spec)
// Sonnets tighten clearance to 1.05× leading so the 14-line body can
// land at 32u under a 50u title. Still satisfies the "gap bigger than
// leading" rule (1.05 > 1.0).
const ABOVE_ATTRIB_CLEARANCE_SONNET = 1.05;
/** Minimum body font size in u. Matches the "25u size floor" in
 *  `dashboard-faces/spec.md` Shared conventions — the only exception is the
 *  battery indicator. Content that still overflows at 25u is signalling that
 *  it doesn't belong on this face; the operator flags it via the review tool
 *  rather than the renderer silently shrinking below legible size. */
const MIN_FONT_U = 25;

export interface FitResult {
  fontSizeU: number;
  cols: number;
}

/** Title-size bucket by character count. 64u display size for short titles,
 *  48u for medium, 36u for long — stops long poem titles overflowing the
 *  top of the face. Raised by `fitGalleryTitle()` below when needed to stay
 *  larger than the body.
 *
 *  Sonnets get a fixed 50u title regardless of length. Body lands at
 *  32u under the 0.70 ratio, the 1.05× sonnet attribution clearance,
 *  and the 0.8× title→body gap. Ratio 32/50 = 0.64. */
function titleSizeBucket(titleLen: number, form?: Form): number {
  if (titleLen === 0) return 0;
  if (form === 'sonnet') return 50;
  return titleLen <= 20 ? 64 : titleLen <= 34 ? 48 : 36;
}

/** Height consumed by the title block at a given size: just the line-box
 *  (font-size × 1.1). The separator below the title is handled by the
 *  .gt-content flex gap (one body leading, in u), which bodyAvailableU
 *  already subtracts as `titleBodyGap`. Earlier revisions added a fixed
 *  24u row-gap here; that was double-counting and cost ~24u of body
 *  budget in every fit. */
function titleHeightU(titleSize: number): number {
  if (titleSize === 0) return 0;
  return Math.ceil(titleSize * 1.1);
}

/** Body size SHALL be at most this fraction of the title size — so the
 *  title reads unambiguously as hierarchy. Equivalent to:
 *    title >= ceil(body / bodyToTitleRatio)
 *  Example: body 52u ⇒ title ≥ 65u (non-sonnet).
 *
 *  Sonnets use a stricter 0.70 (body ≤ 70% of title). The form's 14-line
 *  body is on the edge of what fits at 1m viewing; the tighter ratio lets
 *  body grow closer to the title without undercutting hierarchy. */
function bodyToTitleRatio(form?: Form): number {
  return form === 'sonnet' ? 0.70 : 0.80;
}

/** Smallest title bump (in u) when the body-ratio rule forces the title
 *  up. Rounds to whole u so we don't produce odd fractional sizes. */
function minTitleForBody(bodySize: number, form?: Form): number {
  return Math.ceil(bodySize / bodyToTitleRatio(form));
}

/** Body vertical budget in u for a given title size, body size, and stanza
 *  count. Mirrors the CSS layout in gallery-text.css: the body fits between
 *  the title (top) and the attribution clearance (bottom), minus stanza
 *  margin overhead between stanzas. */
function bodyAvailableU(titleSize: number, bodySize: number, stanzaCount: number, form?: Form): number {
  const titleBlock = titleSize > 0 ? titleHeightU(titleSize) : 0;
  const titleBodyGap = titleSize > 0 ? bodySize * LINE_HEIGHT_FACTOR * TITLE_BODY_GAP_FACTOR : 0;
  const clearanceFactor = form === 'sonnet' ? ABOVE_ATTRIB_CLEARANCE_SONNET : ABOVE_ATTRIB_CLEARANCE;
  const aboveAttribGap = bodySize * LINE_HEIGHT_FACTOR * clearanceFactor;
  const stanzaOverhead =
    Math.max(0, stanzaCount - 1) * bodySize * LINE_HEIGHT_FACTOR * STANZA_MARGIN_FACTOR;
  return (
    FACE_HEIGHT_U -
    TOP_PAD_U -
    titleBlock -
    titleBodyGap -
    aboveAttribGap -
    ATTRIB_HEIGHT_U -
    ATTRIB_BOTTOM_U -
    stanzaOverhead
  );
}

function fitBody(totalLines: number, maxChars: number, form: Form,
                 titleSize: number, stanzaCount: number): FitResult {
  const baseSize = FORMS[form].size;
  const defaultCols = columnCount(totalLines);
  const fits = (size: number, cols: number): boolean => {
    const colWidthU =
      (CONTENT_WIDTH_U - COLUMN_GAP_U * (cols - 1)) / cols;
    const worstLineU = maxChars * size * AVG_CHAR_WIDTH_FACTOR;
    if (worstLineU > colWidthU) return false;
    const linesPerCol = Math.ceil(totalLines / Math.max(cols, 1));
    const stackedU = linesPerCol * size * LINE_HEIGHT_FACTOR;
    const available = bodyAvailableU(titleSize, size, stanzaCount, form);
    return stackedU <= available;
  };
  for (const cols of [defaultCols, Math.max(defaultCols, 2)]) {
    if (fits(baseSize, cols)) return { fontSizeU: baseSize, cols };
  }
  // 1u steps (was 2u) — for tight vertical budgets like 14-line sonnets
  // the extra 1u of resolution is the difference between body at 28u
  // vs body at 29u. With bodyAvailableU accurate, 1u steps don't
  // introduce false positives.
  for (let size = baseSize - 1; size >= MIN_FONT_U; size -= 1) {
    for (const cols of [1, 2]) {
      if (fits(size, cols)) return { fontSizeU: size, cols };
    }
  }
  // Floor — the face overflows visibly; operator flags it.
  return { fontSizeU: MIN_FONT_U, cols: 1 };
}

export function fitGalleryText(
  lines: string[],
  form: Form,
  titleLen = 0,
  stanzaCount = 1,
): FitResult {
  const stripped = lines.filter((l) => l.trim().length > 0);
  const totalLines = stripped.length;
  const maxChars = totalLines === 0
    ? 0
    : Math.max(...stripped.map((l) => l.length));
  // Provisional title size from length bucket (form-aware — sonnets get 42u).
  let titleSize = titleSizeBucket(titleLen, form);
  let bodyFit = fitBody(totalLines, maxChars, form, titleSize, stanzaCount);

  // Invariant: body ≤ bodyToTitleRatio(form) × title. If the length bucket
  // put the title too small relative to the body, bump the title and refit
  // body with the shrunken vertical budget. Iterate up to 3× to guarantee
  // termination.
  for (let i = 0; i < 3; i++) {
    if (titleLen === 0) break;
    if (titleSize >= minTitleForBody(bodyFit.fontSizeU, form)) break;
    titleSize = minTitleForBody(bodyFit.fontSizeU, form);
    bodyFit = fitBody(totalLines, maxChars, form, titleSize, stanzaCount);
  }
  return bodyFit;
}

/** Title opsz that tracks title size. Fraunces' display axis (opsz 144)
 *  reads fragile at ≤60u and oversharp at ≥84u. Scale the opsz axis so the
 *  apertures stay on a reading/display balance across the title-size range:
 *  opsz 96 at ≤60u, opsz 144 at ≥72u, linear in between. */
export function titleOpsz(titleSize: number): number {
  if (titleSize <= 60) return 96;
  if (titleSize >= 72) return 144;
  const t = (titleSize - 60) / 12;
  return Math.round(96 + t * 48);
}

/** Returns the title size gallery.ts should actually use, resolving the
 *  body-fit invariant in a single call. Form-aware so sonnets pick up
 *  the compact 42u bucket and the stricter 0.70 ratio. */
export function fitGalleryTitle(titleLen: number, bodySize: number, form?: Form): number {
  if (titleLen === 0) return 0;
  const bucket = titleSizeBucket(titleLen, form);
  return Math.max(bucket, minTitleForBody(bodySize, form));
}

/** Short-text forms (haiku, tanka, quote, aphorism) get a much larger title
 *  since the body is compact and there's generous vertical space. The ≤20-char
 *  bucket is deliberately heroic (104u ≈ 2× a 52u aphorism body) — at 84u
 *  the title sat too close to body size and read as "another stanza" instead
 *  of as the title. */
export function fitShortFormTitle(titleLen: number, bodySize: number): number {
  if (titleLen === 0) return 0;
  const bucket = titleLen <= 20 ? 104 : titleLen <= 34 ? 80 : titleLen <= 48 ? 60 : 48;
  return Math.max(bucket, minTitleForBody(bodySize));
}
