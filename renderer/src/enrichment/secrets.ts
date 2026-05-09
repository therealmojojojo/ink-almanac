import fs from 'node:fs/promises';
import path from 'node:path';
import { ROOT } from '../config.js';
import { log } from '../logger.js';

/** Spotify Client Credentials + MusicBrainz politeness header, read once at
 *  startup from `ha/secrets.yaml`. The renderer already reads `ha_base_url`
 *  and `ha_long_lived_token` from the same file via plain regex; we follow
 *  that pattern here rather than introducing a YAML parser dependency. */
export interface EnrichmentSecrets {
  spotifyClientId: string;
  spotifyClientSecret: string;
  musicbrainzUserAgent: string;
}

let cached: EnrichmentSecrets | null | undefined;

function pluck(content: string, key: string): string {
  const m = content.match(new RegExp(`^${key}:\\s*"?([^"\\n]+?)"?\\s*$`, 'm'));
  return m?.[1]?.trim() ?? '';
}

/** Read enrichment secrets. Returns `null` if any field is missing or the file
 *  can't be read — the caller treats that as "enrichment disabled" and skips
 *  external lookups, leaving the publisher's flat fields to drive the layout. */
export async function loadEnrichmentSecrets(): Promise<EnrichmentSecrets | null> {
  if (cached !== undefined) return cached;
  const file = path.resolve(ROOT, '..', 'ha', 'secrets.yaml');
  try {
    const content = await fs.readFile(file, 'utf-8');
    const id = pluck(content, 'spotify_client_id');
    const secret = pluck(content, 'spotify_client_secret');
    const ua = pluck(content, 'musicbrainz_user_agent');
    if (!id || !secret || !ua) {
      log.warn(
        { hasId: !!id, hasSecret: !!secret, hasUa: !!ua },
        'enrichment secrets incomplete in ha/secrets.yaml; enrichment disabled',
      );
      cached = null;
      return null;
    }
    cached = { spotifyClientId: id, spotifyClientSecret: secret, musicbrainzUserAgent: ua };
    return cached;
  } catch (err) {
    log.warn({ err }, 'enrichment secrets unreadable; enrichment disabled');
    cached = null;
    return null;
  }
}
