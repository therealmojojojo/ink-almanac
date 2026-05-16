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

/** Strip Spotify's stock edition suffixes from track and album names —
 *  hyphen form on tracks ("Heroes - 2017 Remaster", " - Live", " - Mono
 *  Version") and parenthetical form on albums ("The Boatman's Call (2011 -
 *  Remaster)", "(Remastered)", "(Deluxe Edition)"). Applied iteratively to
 *  handle stacked suffixes ("Track - Remastered 2021 - Live"). Conservative:
 *  the hyphen form requires a leading ` - ` separator and the parenthetical
 *  form requires the noise keyword inside `()` at end-of-string, so legit
 *  hyphenated titles ("Comfortably Numb - Pulse") and legit parentheticals
 *  ("Symphony No. 9 (Choral)") survive. */
const SPOTIFY_SUFFIX_RE = new RegExp(
  '\\s+-\\s+(?:' +
    'Remastered(?:\\s+\\d{4})?|' +
    '\\d{4}\\s+Remaster(?:ed)?|' +
    'Mono(?:\\s+Version)?|' +
    'Stereo(?:\\s+Version)?|' +
    'Live(?:\\s+(?:at|in|from)\\s+.+|\\s+Version)?|' +
    'Single\\s+Version|' +
    'Album\\s+Version|' +
    'Radio\\s+Edit|' +
    'Bonus\\s+Track|' +
    'Deluxe(?:\\s+Edition)?|' +
    'Acoustic(?:\\s+Version)?|' +
    'Extended(?:\\s+Version)?|' +
    'Take\\s+\\d+|' +
    'Edit' +
    ')\\s*$',
  'i',
);

const SPOTIFY_EDITION_PAREN_RE = new RegExp(
  '\\s+\\(' +
    '(?:\\d{4}\\s*-\\s*)?' +
    '(?:' +
      'Remaster(?:ed)?(?:\\s+Version)?|' +
      '\\d{4}\\s+Remaster(?:ed)?|' +
      'Mono(?:\\s+Version)?|' +
      'Stereo(?:\\s+Version)?|' +
      'Live(?:\\s+at\\s+[^)]+|\\s+Version)?|' +
      'Single\\s+Version|' +
      'Album\\s+Version|' +
      'Radio\\s+Edit|' +
      'Bonus\\s+Track|' +
      'Deluxe(?:\\s+Edition)?|' +
      'Acoustic(?:\\s+Version)?|' +
      'Extended(?:\\s+Version)?|' +
      'Anniversary(?:\\s+Edition)?|' +
      'Reissue|' +
      'Special\\s+Edition' +
    ')' +
  '\\)\\s*$',
  'i',
);

export function cleanSpotifyTitle(title: string): string {
  let s = title.trim();
  for (let i = 0; i < 4; i++) {
    const next = s.replace(SPOTIFY_SUFFIX_RE, '').replace(SPOTIFY_EDITION_PAREN_RE, '').trim();
    if (next === s) break;
    s = next;
  }
  return s;
}

/** MB `work.type` values that mark a piece as classical. Anything outside
 *  this set (including the catch-all "Song" used for popular music) does
 *  not by itself qualify a track for the classical layout. */
const CLASSICAL_WORK_TYPES = new Set([
  'Symphony', 'Sonata', 'Sonatina', 'Concerto', 'Quartet', 'Quintet',
  'Trio', 'Sextet', 'Septet', 'Octet', 'Suite', 'Mass', 'Requiem',
  'Opera', 'Operetta', 'Cantata', 'Oratorio', 'Aria', 'Étude', 'Etude',
  'Prelude', 'Fugue', 'Nocturne', 'Mazurka', 'Polonaise', 'Waltz',
  'Sarabande', 'Allemande', 'Gigue', 'Variations', 'Variation',
  'Impromptu', 'Ballade', 'Scherzo', 'Madrigal', 'Motet', 'Lied',
  'Song cycle', 'Tone poem', 'Symphonic poem', 'Overture', 'Rondo',
  'Toccata', 'Capriccio', 'Rhapsody', 'Chant', 'Chorale', 'Movement',
  'Partita',
]);

/** Instrument and voice roles, matched against MB artist `disambiguation`.
 *  Conductor is intentionally absent here — it's resolved separately, by
 *  context (see `roleFor`), because many concert artists are tagged
 *  "pianist and conductor" / "violinist and conductor" and we want the
 *  instrument to win on solo and chamber recordings. */
const DISAMBIG_TO_ROLE: [RegExp, string][] = [
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
 *  their type is already in the name (Quartet/Choir/Orchestra).
 *
 *  `hasEnsemble` tells the function whether the recording's artist-credit
 *  list includes an orchestra or choir. When it does, an artist tagged
 *  "X and conductor" is almost certainly conducting — emit `Cond.` and
 *  skip the instrument match. When it doesn't, the recording is solo /
 *  chamber and the instrument match wins (Barenboim-as-pianist on a Liszt
 *  Consolation, not Barenboim-as-conductor on a Beethoven symphony). */
export function roleFor(artist: MbArtistRef, hasEnsemble = false): string {
  if (!artist) return '';
  if (artist.type === 'Orchestra' || artist.type === 'Choir') return '';
  const disambig = artist.disambiguation ?? '';
  if (hasEnsemble && /\bconductor\b/i.test(disambig)) return 'Cond.';
  for (const [rgx, label] of DISAMBIG_TO_ROLE) {
    if (rgx.test(disambig)) return label;
  }
  if (/\bconductor\b/i.test(disambig)) return 'Cond.';
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
 *  Positive signals (any one is enough):
 *    1. MB work has a composer AND the work `type` is in
 *       CLASSICAL_WORK_TYPES (Symphony/Sonata/Concerto/...). The composer-
 *       presence-alone signal we used to rely on is too permissive — MB now
 *       carries work entries with songwriter-as-composer for most charting
 *       pop and rock songs (Bowie, Velvet Underground, etc.).
 *    2. MB work has a composer, no `type`, BUT the Spotify title shape is
 *       unmistakably classical (Op./BWV/K./Symphony/Nocturne/...). Catches
 *       Satie/Chopin recordings where MB hasn't typed the work.
 *    3. MB has typed performer disambiguations (cellist/pianist/cond./etc.)
 *       or ensemble types (Orchestra/Choir). "Group" is intentionally
 *       excluded — every rock band is "Group" in MB.
 *    4. Spotify lists ≥2 artists AND the title matches a classical shape. */
export function isClassical(opts: {
  mbWorkType?: string | null;
  mbWorkComposer?: string | null;
  recording?: MbRecording | null;
  spotifyArtists?: { name: string }[];
  spotifyTitle?: string;
}): boolean {
  if (opts.mbWorkComposer) {
    if (opts.mbWorkType && CLASSICAL_WORK_TYPES.has(opts.mbWorkType)) return true;
    if (!opts.mbWorkType && opts.spotifyTitle && CLASSICAL_TITLE_SHAPE.test(opts.spotifyTitle)) {
      return true;
    }
    // Composer present but the work is typed non-classical (typically
    // "Song"). Fall through — other signals can still classify it.
  }

  const credits = opts.recording?.['artist-credit'] ?? [];
  const mbInstrumentSignal = credits.some((c) => {
    const t = c.artist?.type;
    if (t === 'Orchestra' || t === 'Choir') return true;
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
