/* Heuristics that decide whether a track is classical, how to split a work
 * title into work + movement, how to label a performer's role from MB type
 * + disambiguation, and how to pick the displayed release year. All pure;
 * no I/O; safe to unit-test in isolation. */

import type { MbArtistRef, MbRecording } from './musicbrainz.js';

const MOVEMENT_PREFIX = /^\s*(?:[IVX]+\.|\d+\.|No\.\s*\d+|[A-Z]\s)/;
const TEMPO_WORDS = new RegExp(
  '\\b(Allegro|Andante|Adagio|Largo|Vivace|Presto|Lento|Moderato|' +
    'Grazioso|Sostenuto|Maestoso|Brio|Cantabile|Espressivo|Scherzo|' +
    'Minuet|Trio|Finale|Pr[ée]lude|Aria|Romance|Tempo)\\b',
  'i',
);

/** Split a track title at the leftmost colon whose suffix looks like a
 *  movement designation (roman/arabic numeral or tempo word). A trailing
 *  colon (MB occasionally appends one) is stripped from the movement.
 *
 *  Examples:
 *    "Symphony No. 5: I. Allegro con brio" → ["Symphony No. 5", "I. Allegro con brio"]
 *    "Six Pieces, Op. 51: VI. Valse"        → ["Six Pieces, Op. 51", "VI. Valse"]
 *    "Nocturne No. 1 in B-Flat Minor"       → ["Nocturne No. 1 in B-Flat Minor", ""]
 *    "String Quartet ... op. 110: 2. ...:"  → ["String Quartet ... op. 110", "2. ..."] */
export function splitWork(title: string): { work: string; movement: string } {
  if (!title.includes(':')) return { work: title, movement: '' };
  const parts = title.split(':');
  for (let i = 1; i < parts.length; i++) {
    const work = parts.slice(0, i).join(':').trim();
    const tail = parts.slice(i).join(':').trim().replace(/:$/, '').trim();
    if (tail && (MOVEMENT_PREFIX.test(tail) || TEMPO_WORDS.test(tail))) {
      return { work, movement: tail };
    }
  }
  return { work: title.replace(/:$/, '').trim(), movement: '' };
}

/** Pick a font-size bucket for the work/track title by character count.
 *  Buckets correspond to font-sizes in `now-playing.css`:
 *    l  → 48u  (≤14 chars)
 *    m  → 38u  (≤22)
 *    s  → 32u  (≤34)
 *    xs → 26u  (otherwise; line-height also tightens) */
export function workBucket(text: string): 'l' | 'm' | 's' | 'xs' {
  const n = [...text].length;
  if (n <= 14) return 'l';
  if (n <= 22) return 'm';
  if (n <= 34) return 's';
  return 'xs';
}

const DISAMBIG_TO_ROLE: [RegExp, string][] = [
  [/\bconductor\b/i, 'Cond.'],
  [/\bpianist\b/i, 'Piano'],
  [/\bcellist\b/i, 'Cello'],
  [/\bviolinist\b/i, 'Violin'],
  [/\bviolist\b/i, 'Viola'],
  [/\bharpsichordist\b/i, 'Harpsi.'],
  [/\borganist\b/i, 'Organ'],
  [/\bguitarist\b/i, 'Guitar'],
  [/\bflautist|flutist\b/i, 'Flute'],
  [/\bsoprano\b/i, 'Sop.'],
  [/\bmezzo\b/i, 'Mezzo'],
  [/\btenor\b/i, 'Ten.'],
  [/\b(operatic )?bass\b/i, 'Bass'],
  [/\bbaritone\b/i, 'Bari.'],
];

/** Map an MB artist ref to a display role chip. Ensembles return '' because
 *  their type is already in the name (Quartet/Choir/Orchestra). */
export function roleFor(artist: MbArtistRef): string {
  if (!artist) return '';
  if (artist.type === 'Orchestra' || artist.type === 'Choir' || artist.type === 'Group') return '';
  for (const [rgx, label] of DISAMBIG_TO_ROLE) {
    if (rgx.test(artist.disambiguation ?? '')) return label;
  }
  return '';
}

/** Pick the earlier year between MB `recording.first-release-date` and
 *  Spotify `album.release_date`. Both can be missing; result is '' when both
 *  are. Both fail towards "more recent" when their underlying catalogue
 *  lacks the original release, so taking the minimum favours whichever
 *  source got the original right. */
export function chooseYear(mbDate: string | undefined | null, spotifyDate: string | undefined | null): string {
  const mb = (mbDate ?? '').slice(0, 4);
  const sp = (spotifyDate ?? '').slice(0, 4);
  if (mb && sp) return mb < sp ? mb : sp;
  return mb || sp || '';
}

/** Catalogue markers and form names that strongly suggest classical when
 *  spotted in a track title (used as a fallback signal when MB has no
 *  recording for the ISRC). */
const CLASSICAL_TITLE_SHAPE = new RegExp(
  '\\b(?:Op|BWV|K|RV|TH|R|D|L|S|WoO|B|Hob|HWV|BB|BV)\\.\\s*\\d|' +
    'Symphony|Concerto|Sonata|Quartet|Quintet|Trio|' +
    'Pr[ée]lude|[ÉE]tude|' +
    'Nocturne|Mazurka|Waltz|Sarabande|Allemande|Gigue|Mass|Fugue|' +
    'Suite|Variations?|Impromptu|Ballade|Polonaise|' +
    'Carnival|Pieces|Songs|Romance|Lied|' +
    'Gymnop[ée]die|Gnossienne|Liebestraum|' +
    ':\\s*[IVX]+\\.|:\\s*\\d+\\.',
);

/** Decide whether a track is classical, given the merged Spotify+MB picture.
 *  Three positive signals (any one is enough):
 *    1. MB has a work-rel and the work has at least one composer
 *    2. MB has typed performer disambiguations (cellist/pianist/cond./etc.)
 *       or ensemble types (Orchestra/Choir/Group)
 *    3. Spotify lists ≥2 artists AND the title matches a classical shape */
export function isClassical(opts: {
  mbWorkComposer?: string | null;
  recording?: MbRecording | null;
  spotifyArtists?: { name: string }[];
  spotifyTitle?: string;
}): boolean {
  if (opts.mbWorkComposer) return true;

  const credits = opts.recording?.['artist-credit'] ?? [];
  const mbInstrumentSignal = credits.some((c) => {
    const t = c.artist?.type;
    if (t === 'Orchestra' || t === 'Choir' || t === 'Group') return true;
    return roleFor(c.artist) !== '';
  });
  if (mbInstrumentSignal) return true;

  const artistsLen = opts.spotifyArtists?.length ?? 0;
  if (artistsLen >= 2 && opts.spotifyTitle && CLASSICAL_TITLE_SHAPE.test(opts.spotifyTitle)) {
    return true;
  }

  // Edge case: only one Spotify artist (the performer), but the title alone
  // is a clear classical work — Cherny / Gnossienne style. Render with no
  // composer line.
  if (opts.spotifyTitle && /\bGymnop[ée]die|Gnossienne|Symphony|Concerto|Sonata|Nocturne|Variations?\b/.test(opts.spotifyTitle)) {
    return true;
  }

  return false;
}
