import fs from 'node:fs/promises';
import path from 'node:path';
import { randomUUID } from 'node:crypto';
import { ROOT } from '../config.js';

/** Disk-backed JSON cache for Spotify/MusicBrainz lookups. Entries are
 *  immutable in practice (recording metadata never changes), so there is no
 *  TTL. Manual reset is `rm -rf renderer/cache/`.
 *
 *  Layout under `renderer/cache/`:
 *    spotify/<spotify_track_id>.json  — Spotify track payload
 *    mb/<isrc>.json                   — MB recording payload (ISRC keyed)
 *    mb-work/<work_mbid>.json         — MB work payload
 *    mb-artist/<artist_mbid>.json     — MB artist payload (with aliases)
 *    enriched/<spotify_track_id>.json — final merged enrichment object */
const CACHE_DIR = process.env.RENDERER_ENRICHMENT_CACHE_DIR
  ?? path.join(ROOT, 'cache');

function fileFor(bucket: string, key: string): string {
  // Sanitise key — Spotify/MB ids are already alnum+dash, but be defensive.
  const safe = key.replace(/[^A-Za-z0-9_.-]/g, '_');
  return path.join(CACHE_DIR, bucket, `${safe}.json`);
}

export async function read<T>(bucket: string, key: string): Promise<T | null> {
  const p = fileFor(bucket, key);
  try {
    const data = await fs.readFile(p, 'utf-8');
    return JSON.parse(data) as T;
  } catch {
    return null;
  }
}

export async function write<T>(bucket: string, key: string, value: T): Promise<void> {
  const p = fileFor(bucket, key);
  await fs.mkdir(path.dirname(p), { recursive: true });
  // Atomic-rename pattern; matches the publisher's tmp+rename in server.ts.
  const tmp = `${p}.${randomUUID()}.tmp`;
  await fs.writeFile(tmp, JSON.stringify(value, null, 2));
  await fs.rename(tmp, p);
}

export async function getOrCompute<T>(
  bucket: string,
  key: string,
  compute: () => Promise<T | null>,
): Promise<T | null> {
  const cached = await read<T>(bucket, key);
  if (cached !== null) return cached;
  const fresh = await compute();
  if (fresh !== null) await write(bucket, key, fresh);
  return fresh;
}
