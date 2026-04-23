/**
 * Extended-grapheme-cluster length via Intl.Segmenter (UAX #29).
 * Counts `"Să"` as 2, not 3 (the UTF-16 length of the decomposed form).
 */
const segmenter = new Intl.Segmenter('und', { granularity: 'grapheme' });

export function graphemeLength(s: string): number {
  let n = 0;
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  for (const _ of segmenter.segment(s)) n++;
  return n;
}

export function graphemeSlice(s: string, n: number): string {
  let out = '';
  let count = 0;
  for (const seg of segmenter.segment(s)) {
    if (count >= n) break;
    out += seg.segment;
    count++;
  }
  return out;
}

export const ELLIPSIS = '\u2026';

/**
 * Hard-cut prose to `maxChars × maxLines − 1` graphemes and append U+2026.
 * Returns the original string if it already fits.
 */
export function truncateProse(
  s: string,
  maxChars: number,
  maxLines: number,
): string {
  const budget = maxChars * maxLines;
  const len = graphemeLength(s);
  if (len <= budget) return s;
  return graphemeSlice(s, budget - 1) + ELLIPSIS;
}
