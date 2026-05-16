import type { DitherMask } from '../image/dither.js';
import { cleanSpotifyTitle, workBucket } from '../enrichment/classify.js';
import { batteryIndicator } from '../templateMacros.js';
import { escapeHtml, htmlShell } from './shell.js';
import type { NowPlayingInput } from './schema.js';

const SOURCE_LABELS: Record<string, string> = {
  spotify: 'SPOTIFY',
  'apple-music': 'APPLE MUSIC',
  airplay: 'AIRPLAY',
  tunein: 'RADIO',
  'line-in': 'LINE IN',
  other: 'OTHER',
};

interface Slots {
  topLabel: string;          // composer (classical) | artist (non-classical)
  work: string;              // work title (classical) | track title (non-classical)
  movement: string;          // italic subtitle, classical only
  /** Bottom strip rows. Classical: performers + optional year row.
   *  Non-classical: album row + optional year row (year on its own line so
   *  the strip reads consistently across both layouts). */
  rows: { role: string; name: string; isYear?: boolean }[];
}

/** Decide which slots get which fields based on the enrichment flag. The
 *  fallback path (classical undefined) reuses the non-classical mapping with
 *  the publisher's flat `title/artist/album` fields, so the existing pop
 *  pipeline keeps working when enrichment is unavailable. */
function pickSlots(s: NowPlayingInput['sonos']): Slots {
  const year = s.first_release_year ?? '';
  if (s.classical) {
    return {
      topLabel: s.composer ?? '',
      work: s.work ?? s.title ?? '',
      movement: s.movement ?? '',
      rows: [
        ...(s.performers ?? []).map((p) => ({ role: p.role, name: p.name })),
        ...(year ? [{ role: '', name: year, isYear: true }] : []),
      ],
    };
  }
  // Non-classical: artist top, track in the work slot, album then year as
  // separate rows (year on its own line, matching the classical layout).
  // Both title and album go through cleanSpotifyTitle so Spotify's stock
  // edition tags ("Red Right Hand - 2021 Remaster", "The Boatman's Call
  // (2011 - Remaster)") don't leak into the display. The classical branch
  // already strips these via splitWork(cleanedTitle) upstream.
  const album = cleanSpotifyTitle(s.album ?? '');
  return {
    topLabel: (s.artist ?? '').toUpperCase(),
    work: cleanSpotifyTitle(s.title ?? ''),
    movement: '',
    rows: [
      ...(album ? [{ role: '', name: album }] : []),
      ...(year ? [{ role: '', name: year, isYear: true }] : []),
    ],
  };
}

export function buildHtml(input: NowPlayingInput): string {
  const s = input.sonos;
  const sourceLabel =
    s.source_indicator ??
    (s.source ? `SONOS · ${SOURCE_LABELS[s.source] ?? s.source.toUpperCase()}` : 'SONOS');
  const slots = pickSlots(s);
  const wb = workBucket(slots.work);

  // Album art: prefer `art_url` (set by the enrichment pipeline to Spotify's
  // CDN URL when reachable, or by HA's publisher to a /ha-proxy URL) over the
  // legacy `art_path`. Either can be absent; the fallback handles a broken
  // image with a graceful onerror swap.
  const artSrc = s.art_url ?? s.art_path ?? '';
  const fallbackArtSrc = '/static/img/now-playing/fallback.jpg';
  const imgSrc = artSrc || fallbackArtSrc;

  const stripRows = slots.rows
    .map((r) => {
      const cls = r.isYear ? 'row year-row' : 'row';
      return `<div class="${cls}"><span class="role">${escapeHtml(r.role)}</span><span class="name">${escapeHtml(r.name)}</span></div>`;
    })
    .join('');

  const body = `
<div class="face np-root">
  ${batteryIndicator(input.device?.battery?.percentage)}
  <section class="np-art">
    <img src="${escapeHtml(imgSrc)}" alt="" onerror="this.onerror=null;this.src='${fallbackArtSrc}'">
  </section>
  <section class="np-right">
    <div class="source">${escapeHtml(sourceLabel)}</div>
    <div class="label-top">${escapeHtml(slots.topLabel)}</div>
    <div class="work" data-size="${wb}">${escapeHtml(slots.work)}</div>
    <div class="movement">${escapeHtml(slots.movement)}</div>
    <div class="strip">${stripRows}</div>
    <div class="np-clock">${escapeHtml(input.clock.time)}</div>
  </section>
</div>`;

  return htmlShell({
    title: 'Now Playing',
    styles: ['/static/css/now-playing.css'],
    body,
  });
}

export function ditherMask(input: NowPlayingInput): boolean | DitherMask {
  if (!input.sonos.art_path && !input.sonos.art_url) return false;
  const W = 1200;
  const H = 825;
  const data = new Uint8Array(W * H);
  // Album art occupies the left 825 columns (the square art zone).
  for (let y = 0; y < H; y++) {
    for (let x = 0; x < 825; x++) data[y * W + x] = 1;
  }
  return { width: W, height: H, data };
}
