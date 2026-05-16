import { log } from '../logger.js';
import * as cache from './cache.js';
import type { EnrichmentSecrets } from './secrets.js';

export interface MbArtistRef {
  id: string;
  name: string;
  type?: string | null;       // "Person", "Orchestra", "Choir", "Group", ...
  disambiguation?: string;
}

export interface MbRecording {
  id: string;
  title: string;
  length?: number;
  'first-release-date'?: string;
  'artist-credit'?: { name: string; joinphrase?: string; artist: MbArtistRef }[];
  relations?: {
    type: string;
    'target-type': string;
    work?: { id: string; title: string };
    artist?: MbArtistRef;
    begin?: string;
    end?: string;
  }[];
}

export interface MbWork {
  id: string;
  title: string;
  /** MB classifies works by form: "Song" for popular music, "Symphony" /
   *  "Sonata" / "Concerto" / "Quartet" / "Aria" / etc. for classical. Used
   *  by `isClassical` as the strongest available gate. */
  type?: string | null;
  relations?: {
    type: string;
    artist?: MbArtistRef;
    'target-type': string;
  }[];
}

export interface MbArtistAlias {
  name: string;
  locale?: string;
  type?: string;
  primary?: boolean;
}

export interface MbArtist {
  id: string;
  name: string;
  aliases?: MbArtistAlias[];
}

/** Single-slot semaphore enforcing ≥1100 ms between MB calls (their TOU asks
 *  for ≤1 req/s; the extra 100 ms guards against clock drift and request
 *  in-flight overlap on busy hosts). FIFO so calls preserve issue order. */
const MB_INTERVAL_MS = 1100;
let mbLastAt = 0;
let mbChain: Promise<unknown> = Promise.resolve();

async function withMbSlot<T>(fn: () => Promise<T>): Promise<T> {
  const next = mbChain.then(async () => {
    const wait = mbLastAt + MB_INTERVAL_MS - Date.now();
    if (wait > 0) await new Promise((r) => setTimeout(r, wait));
    mbLastAt = Date.now();
    return fn();
  });
  // Keep the chain alive even if `next` rejects.
  mbChain = next.then(
    () => undefined,
    () => undefined,
  );
  return next;
}

async function mbFetch<T>(url: string, secrets: EnrichmentSecrets): Promise<T | null> {
  return withMbSlot(async () => {
    const res = await fetch(url, {
      headers: { 'User-Agent': secrets.musicbrainzUserAgent, Accept: 'application/json' },
    });
    if (res.status === 404) return null;
    if (res.status === 503) {
      // Honour Retry-After once, up to 5 s; longer than that we just bail.
      const ra = parseInt(res.headers.get('retry-after') ?? '0', 10);
      const wait = Math.min(Math.max(ra * 1000, 1000), 5000);
      await new Promise((r) => setTimeout(r, wait));
      const retry = await fetch(url, {
        headers: { 'User-Agent': secrets.musicbrainzUserAgent, Accept: 'application/json' },
      });
      if (!retry.ok) return null;
      return (await retry.json()) as T;
    }
    if (!res.ok) {
      log.warn({ url, status: res.status }, 'musicbrainz lookup failed');
      return null;
    }
    return (await res.json()) as T;
  });
}

/** Look up a recording by ISRC, including artist credits and work-rels. */
export async function byISRC(isrc: string, secrets: EnrichmentSecrets): Promise<MbRecording | null> {
  if (!isrc) return null;
  return cache.getOrCompute<MbRecording>('mb', isrc, async () => {
    const url = `https://musicbrainz.org/ws/2/isrc/${encodeURIComponent(isrc)}?inc=work-rels+artist-credits&fmt=json`;
    const data = await mbFetch<{ recordings?: MbRecording[] }>(url, secrets);
    return data?.recordings?.[0] ?? null;
  });
}

/** Look up a work by MBID with composer relations populated. */
export async function getWork(workMbid: string, secrets: EnrichmentSecrets): Promise<MbWork | null> {
  if (!workMbid) return null;
  return cache.getOrCompute<MbWork>('mb-work', workMbid, async () => {
    const url = `https://musicbrainz.org/ws/2/work/${workMbid}?inc=artist-rels&fmt=json`;
    return mbFetch<MbWork>(url, secrets);
  });
}

/** Look up an artist by MBID with locale aliases populated — used to find
 *  Latin transliterations of non-Latin composer names. */
export async function getArtist(artistMbid: string, secrets: EnrichmentSecrets): Promise<MbArtist | null> {
  if (!artistMbid) return null;
  return cache.getOrCompute<MbArtist>('mb-artist', artistMbid, async () => {
    const url = `https://musicbrainz.org/ws/2/artist/${artistMbid}?inc=aliases&fmt=json`;
    return mbFetch<MbArtist>(url, secrets);
  });
}
