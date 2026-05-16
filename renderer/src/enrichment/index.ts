import { log } from '../logger.js';
import * as cache from './cache.js';
import { chooseYear, cleanSpotifyTitle, isClassical, roleFor, splitWork } from './classify.js';
import type { MbArtistRef } from './musicbrainz.js';
import * as mb from './musicbrainz.js';
import { loadEnrichmentSecrets } from './secrets.js';
import { extractSpotifyId, getTrack } from './spotify.js';

/** Final enriched payload merged into `inputs/sonos.json`. All fields
 *  optional from a schema standpoint; absent fields make the renderer fall
 *  back to today's flat title/artist/album rendering. */
export interface Enrichment {
  classical: boolean;
  composer?: string;
  work?: string;
  movement?: string;
  performers?: { name: string; role: string }[];
  first_release_year?: string;
  /** Convenient art URL straight from Spotify; published as `art_url` so
   *  the existing template macro picks it up without changes. */
  art_url?: string;
}

/** Resolve a Latin-friendly composer name. Order:
 *    1. If Spotify lists an artist with a similar name (case-insensitive),
 *       trust Spotify (Spotify always uses Latin).
 *    2. Otherwise fetch the MB artist's aliases and pick the first
 *       `locale: en, primary: true` one.
 *    3. Fall back to the raw MB composer name (may be in source script). */
async function resolveComposerLatin(
  rawName: string,
  composerArtistRef: MbArtistRef | undefined,
  spotifyArtistNames: string[],
  secrets: { musicbrainzUserAgent: string },
): Promise<string> {
  if (!rawName) return '';

  // Step 1 — direct Spotify match by name (case-insensitive). Cheap.
  const lc = rawName.toLowerCase();
  const direct = spotifyArtistNames.find((n) => n.toLowerCase() === lc);
  if (direct) return direct;

  // Heuristic: if name only contains ASCII letters, it's already Latin —
  // no need to fetch aliases.
  if (/^[\x20-\x7EÀ-ɏ]+$/.test(rawName)) return rawName;

  // Step 2 — MB artist aliases.
  if (composerArtistRef?.id) {
    const artist = await mb.getArtist(composerArtistRef.id, secrets as never);
    const aliases = artist?.aliases ?? [];
    const en = aliases.find((a) => a.locale === 'en' && a.primary);
    if (en?.name) return en.name;
    // Fallback: any en alias, primary or not.
    const anyEn = aliases.find((a) => a.locale === 'en');
    if (anyEn?.name) return anyEn.name;
  }

  return rawName;
}

/** Run the full enrichment pipeline for a Spotify track id. Cached on disk
 *  by track id so subsequent encounters are essentially free. Returns null
 *  if the secrets aren't configured or every external call fails. */
export async function enrich(spotifyId: string): Promise<Enrichment | null> {
  const secrets = await loadEnrichmentSecrets();
  if (!secrets) return null;

  return cache.getOrCompute<Enrichment>('enriched', spotifyId, async () => {
    const track = await getTrack(spotifyId, secrets);
    if (!track) return null;

    const isrc = track.external_ids?.isrc ?? '';
    const recording = isrc ? await mb.byISRC(isrc, secrets) : null;

    // Find a work-rel; follow it for canonical composer + work type.
    let workRelTitle = '';
    let workType: string | null = null;
    let workComposer: string | null = null;
    let workComposerRef: MbArtistRef | undefined;
    if (recording?.relations) {
      for (const r of recording.relations) {
        if (r['target-type'] === 'work' && r.work) {
          const work = await mb.getWork(r.work.id, secrets);
          const composerRel = work?.relations?.find((wr) => wr.type === 'composer');
          if (composerRel?.artist) {
            workComposer = composerRel.artist.name;
            workComposerRef = composerRel.artist;
            workRelTitle = work?.title ?? r.work.title;
            workType = work?.type ?? null;
            break;
          }
        }
      }
    }

    const cleanedTitle = cleanSpotifyTitle(track.name);

    const classical = isClassical({
      mbWorkType: workType,
      mbWorkComposer: workComposer,
      recording,
      spotifyArtists: track.artists,
      spotifyTitle: cleanedTitle,
    });

    // Composer: from MB work-rel when available, else from Spotify's first
    // artist when classical and 2+ artists were listed (the canonical
    // composer-first convention on Spotify classical entries).
    let composer = '';
    if (workComposer) {
      composer = await resolveComposerLatin(
        workComposer,
        workComposerRef,
        track.artists.map((a) => a.name),
        secrets,
      );
    } else if (classical && track.artists.length >= 2) {
      composer = track.artists[0]!.name;
    }

    // Work + movement from Spotify's title (familiar capitalisation; MB's is
    // sometimes structurally cleaner but inconsistent across entries).
    // Suffix-cleaned so " - Remastered 2021" / " - Live" don't leak in.
    const { work, movement } = splitWork(cleanedTitle);

    // Performers: MB recording's typed credits when present; otherwise fall
    // back to Spotify's artists[] minus the inferred composer. Drop credits
    // that aren't in Spotify's list (cuts opera-cast bloat).
    const spotifyNames = new Set(track.artists.map((a) => a.name.toLowerCase()));
    const performers: { name: string; role: string }[] = [];
    const credits = recording?.['artist-credit'] ?? [];
    // Whether the recording itself carries an ensemble — decides whether
    // a "pianist and conductor"-style disambiguation should resolve to
    // their instrument (no ensemble, solo / chamber recording) or to
    // 'Cond.' (ensemble present, podium context).
    const hasEnsemble = credits.some((c) => {
      const t = c.artist?.type;
      return t === 'Orchestra' || t === 'Choir';
    });
    if (credits.length > 0) {
      for (const c of credits) {
        if (composer && c.name.toLowerCase() === composer.toLowerCase()) continue;
        if (spotifyNames.size > 0 && !spotifyNames.has(c.name.toLowerCase())) continue;
        performers.push({ name: c.name, role: roleFor(c.artist, hasEnsemble) });
      }
    }
    if (performers.length === 0 && track.artists.length > 0) {
      for (const a of track.artists) {
        if (composer && a.name.toLowerCase() === composer.toLowerCase()) continue;
        performers.push({ name: a.name, role: '' });
      }
    }

    const first_release_year = chooseYear(
      recording?.['first-release-date'] ?? '',
      track.album.release_date ?? '',
    );

    // Prefer MB's recording title for the work display when present and it
    // already strips the "Composer / Arr.: " prefix Spotify often duplicates
    // — but only when the MB title is shorter (a rough heuristic that the
    // MB version is cleaner). Otherwise stick with Spotify's title.
    const workOut =
      workRelTitle && workRelTitle.length < work.length ? splitWork(workRelTitle).work : work;

    const art = track.album.images?.[0]?.url ?? '';

    // Build with `exactOptionalPropertyTypes` in mind: only set optional
    // fields that are actually present.
    const result: Enrichment = { classical };
    if (composer) result.composer = composer;
    if (classical && workOut) result.work = workOut;
    if (classical && movement) result.movement = movement;
    if (classical && performers.length > 0) result.performers = performers;
    if (first_release_year) result.first_release_year = first_release_year;
    if (art) result.art_url = art;
    log.info(
      { spotifyId, classical, composer, work: workOut, year: first_release_year },
      'enrichment computed',
    );
    return result;
  });
}

/** Convenience: extract a Spotify track id from a Sonos `media_content_id`
 *  and run enrichment. Returns null when the input isn't Spotify-sourced or
 *  enrichment fails. */
export async function enrichFromSonos(sonos: { media_content_id?: string | null }): Promise<Enrichment | null> {
  const id = extractSpotifyId(sonos.media_content_id);
  if (!id) return null;
  return enrich(id);
}
