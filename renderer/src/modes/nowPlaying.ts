import type { DitherMask } from '../image/dither.js';
import { batteryIndicator } from '../templateMacros.js';
import { applyZone } from '../zoneApply.js';
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

/** Pick a title size bucket that keeps longer track names readable without
 * cropping. Thresholds are tuned against the right column's available width
 * (~324 u after padding) and Fraunces 500's metrics. See now-playing.css
 * for the corresponding font-size values. */
function titleSizeBucket(title: string): 'l' | 'm' | 's' | 'xs' {
  // Use extended-grapheme length (same metric the zone budget uses).
  const n = [...title].length;
  if (n <= 14) return 'l';
  if (n <= 22) return 'm';
  if (n <= 32) return 's';
  return 'xs';
}

export function buildHtml(input: NowPlayingInput): string {
  const s = input.sonos;
  const sourceLabel =
    s.source_indicator ??
    (s.source ? `SONOS · ${SOURCE_LABELS[s.source] ?? s.source.toUpperCase()}` : 'SONOS');
  const title = applyZone('np_title', s.title ?? '—');
  const artist = applyZone('np_artist', (s.artist ?? '—').toUpperCase());
  const album = applyZone('np_album', s.album ?? '');
  const titleSize = titleSizeBucket(title);

  // Prefer `art_url` (HTTP fetch at render time by Chromium) over `art_path`
  // (local file from the legacy SSH-based publisher). Either can be absent,
  // and the upstream chain (HA media_player_proxy → Sonos getaa) intermittently
  // returns errors / empty bytes for some Spotify tracks. The `<img>` tag uses
  // the local fallback both as the initial src when artSrc is empty and via
  // an onerror swap when art_url fails to load — so the panel always shows
  // *something* aesthetic in the art zone instead of a broken-image icon.
  const artSrc = s.art_url ?? s.art_path ?? '';
  const fallbackArtSrc = '/static/img/now-playing/fallback.jpg';
  const imgSrc = artSrc || fallbackArtSrc;
  const body = `
<div class="face np-root">
  ${batteryIndicator(input.device?.battery?.percentage)}
  <section class="np-art">
    <img src="${escapeHtml(imgSrc)}" alt="" onerror="this.onerror=null;this.src='${fallbackArtSrc}'">
  </section>
  <section class="np-right">
    <div class="source">${escapeHtml(applyZone('np_source', sourceLabel))}</div>
    <div class="text">
      <div class="title" data-size="${titleSize}">${escapeHtml(title)}</div>
      <div class="artist">${escapeHtml(artist)}</div>
      ${album ? `<div class="album">${escapeHtml(album)}</div>` : ''}
    </div>
    ${
      s.next_track
        ? `<div class="next">
  <div class="label">Next</div>
  <div class="track">${escapeHtml(applyZone('np_next', s.next_track))}</div>
</div>`
        : ''
    }
  </section>
  <div class="np-clock">${escapeHtml(input.clock.time)}</div>
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
