import { graphemeLength, truncateProse } from './text.js';
import { ZONES, type ZoneId } from './zones.js';

export class VerseOverflowError extends Error {
  readonly code = 'VERSE_OVERFLOW' as const;
  constructor(
    readonly zoneId: ZoneId,
    readonly inputLength: number,
    readonly budget: number,
  ) {
    super(`verse zone ${zoneId} overflows: ${inputLength} > ${budget}`);
  }
}

/**
 * Apply a zone budget. Prose → hard-truncate with ellipsis.
 * Verse → throw VerseOverflowError (caller maps to HTTP 422).
 */
export function applyZone(id: ZoneId, input: string): string {
  const z = ZONES[id];
  if (z.kind === 'prose') {
    return truncateProse(input, z.maxChars, z.maxLines);
  }
  // verse: reject overflow line-by-line and total.
  // Trim leading/trailing blank lines so a trailing '\n' (almost universal in
  // YAML block scalars) doesn't count as an extra line.
  const trimmed = input.replace(/^(?:\r?\n)+/, '').replace(/(?:\r?\n)+$/, '');
  const lines = trimmed.split(/\r?\n/);
  if (lines.length > z.maxLines) {
    throw new VerseOverflowError(id, lines.length, z.maxLines);
  }
  for (const line of lines) {
    const n = graphemeLength(line);
    if (n > z.maxChars) {
      throw new VerseOverflowError(id, n, z.maxChars);
    }
  }
  return trimmed;
}
