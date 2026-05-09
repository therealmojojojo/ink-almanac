import { log } from '../logger.js';
import * as cache from './cache.js';
import type { EnrichmentSecrets } from './secrets.js';

/** Spotify track payload — only the fields we read downstream. The whole
 *  response is cached, so adding fields later is non-breaking. */
export interface SpotifyTrack {
  id: string;
  name: string;
  external_ids?: { isrc?: string };
  artists: { id: string; name: string }[];
  album: {
    id: string;
    name: string;
    release_date?: string;
    images?: { url: string; width?: number; height?: number }[];
  };
}

/** App-level token cache — one bearer per renderer process, refreshed on
 *  expiry. Mutex keeps two concurrent enrichments from refreshing twice. */
let tokenState: { value: string; expiresAt: number } | null = null;
let inflight: Promise<string> | null = null;

async function fetchToken(secrets: EnrichmentSecrets): Promise<string> {
  const auth = Buffer.from(
    `${secrets.spotifyClientId}:${secrets.spotifyClientSecret}`,
  ).toString('base64');
  const res = await fetch('https://accounts.spotify.com/api/token', {
    method: 'POST',
    headers: {
      Authorization: `Basic ${auth}`,
      'Content-Type': 'application/x-www-form-urlencoded',
    },
    body: 'grant_type=client_credentials',
  });
  if (!res.ok) {
    throw new Error(`spotify token: ${res.status} ${res.statusText}`);
  }
  const body = (await res.json()) as { access_token: string; expires_in: number };
  // Subtract 60 s of safety margin to avoid using a token mid-expiry.
  tokenState = {
    value: body.access_token,
    expiresAt: Date.now() + (body.expires_in - 60) * 1000,
  };
  log.info({ ttl: body.expires_in }, 'spotify token acquired');
  return tokenState.value;
}

async function getToken(secrets: EnrichmentSecrets): Promise<string> {
  if (tokenState && Date.now() < tokenState.expiresAt) return tokenState.value;
  if (inflight) return inflight;
  inflight = fetchToken(secrets).finally(() => {
    inflight = null;
  });
  return inflight;
}

/** Look up a Spotify track by id, caching the response indefinitely.
 *  Returns null on 4xx/5xx (caller falls back to publisher's flat fields). */
export async function getTrack(
  spotifyId: string,
  secrets: EnrichmentSecrets,
): Promise<SpotifyTrack | null> {
  return cache.getOrCompute<SpotifyTrack>('spotify', spotifyId, async () => {
    const token = await getToken(secrets);
    const res = await fetch(`https://api.spotify.com/v1/tracks/${spotifyId}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (res.status === 401) {
      // Token rejected — clear and retry once with a fresh one.
      tokenState = null;
      const fresh = await getToken(secrets);
      const retry = await fetch(`https://api.spotify.com/v1/tracks/${spotifyId}`, {
        headers: { Authorization: `Bearer ${fresh}` },
      });
      if (!retry.ok) {
        log.warn({ id: spotifyId, status: retry.status }, 'spotify track lookup failed');
        return null;
      }
      return (await retry.json()) as SpotifyTrack;
    }
    if (!res.ok) {
      log.warn({ id: spotifyId, status: res.status }, 'spotify track lookup failed');
      return null;
    }
    return (await res.json()) as SpotifyTrack;
  });
}

/** Extract a Spotify track id from a Sonos `media_content_id`. The Sonos
 *  Spotify URI is shaped `x-sonos-spotify:spotify%3atrack%3a<ID>?...` (with
 *  URL-encoded colons). Returns null when the input isn't a Spotify track. */
export function extractSpotifyId(mediaContentId: string | null | undefined): string | null {
  if (!mediaContentId) return null;
  // Match either the percent-encoded form Sonos uses, or a plain spotify:track:
  const m = mediaContentId.match(/spotify(?:%3a|:)track(?:%3a|:)([A-Za-z0-9]{22})/);
  return m?.[1] ?? null;
}
