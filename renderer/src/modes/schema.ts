import { z } from 'zod';

const temp = z.object({ c: z.number(), f: z.number().optional() });

export const weatherInput = z.object({
  locations: z
    .array(
      z.object({
        name: z.string(),
        current: z.object({
          condition: z.string(),
          icon: z.string().optional(),
          temp: temp,
        }),
        forecast: z
          .array(
            z.object({
              day: z.string(),
              high: temp,
              low: temp,
              condition: z.string(),
              icon: z.string().optional(),
            }),
          )
          .max(7),
        /** Short-term precipitation nowcast, derived upstream (HA side) from
         *  hourly forecast data. When present, the Summary / Night faces
         *  surface `label` as a short mono-caps line; when absent, the line
         *  is hidden. `minutes_until_change` is optional metadata (not
         *  rendered directly) describing when the predicted state change
         *  happens, for renderers that want to stagger the message. */
        nowcast: z
          .object({
            label: z.string(),
            minutes_until_change: z.number().int().nullable().optional(),
          })
          .optional(),
      }),
    )
    .min(1)
    .max(2),
  astro: z
    .object({
      event: z.object({ title: z.string(), detail: z.string(), when: z.string() }),
      moon: z.object({ phase: z.string(), illumination: z.number().min(0).max(1) }),
      sun: z.object({ rise: z.string(), set: z.string() }).optional(),
    })
    .optional(),
  poetic: z.string().optional(),
});

// NOTE: `climateInput` was removed — the product decision is to not ship any
// indoor-climate sensor. Summary's three-band composition now excludes the
// INSIDE zone. If a kitchen sensor is ever added, reintroduce the schema +
// the publisher + a new zone in a follow-up change.

/** Device state: battery + build + last_seen. Optional at the schema level —
 *  missing `device.json` renders the battery indicator with its graceful
 *  em-dash treatment (dashboard-faces §Shared conventions). */
export const deviceInput = z.object({
  battery: z.object({
    percentage: z.number().min(0).max(100),
    voltage: z.number().optional(),
  }),
  build: z.string().optional(),
  last_seen: z.string().optional(),
});

export const sonosInput = z.object({
  next_track: z.string().optional(),
  state: z.enum(['playing', 'paused', 'idle']),
  title: z.string().optional(),
  artist: z.string().optional(),
  album: z.string().optional(),
  /** Local filesystem path to the album art (legacy path — used when HA
   *  pre-downloads the art to the Mac). Preferred by the template only if
   *  `art_url` is absent. */
  art_path: z.string().optional(),
  /** Absolute HTTP URL to the album art. Used when HA publishes the
   *  Sonos entity_picture URL directly and Chromium fetches at render time.
   *  This is the current (HTTP-only) path. */
  art_url: z.string().optional(),
  source: z.enum(['spotify', 'apple-music', 'airplay', 'tunein', 'line-in', 'other']).optional(),
  /** Pre-formatted source indicator (e.g., "SONOS · SPOTIFY"). When present,
   *  overrides the renderer's source→label mapping. HA writes this via the
   *  now_playing_sources.yaml mapping so new sources can be added without a
   *  renderer deploy. */
  source_indicator: z.string().optional(),
});

export const newsInput = z.object({
  items: z.array(z.object({ body: z.string() })).max(1),
});

const form = z.enum([
  'haiku',
  'tanka',
  'sonnet',
  'free-verse',
  'stanzaic',
  'fragment',
  'aphorism',
  'prose-poem',
  'quote',
]);

export const pairingInput = z.object({
  date: z.string(),
  theme: z.string().optional(),
  gallery: z.object({
    flavor: z.enum(['visual', 'text']),
    visual: z
      .object({
        image_path: z.string(),
        title: z.string(),
        artist: z.string(),
        year: z.string().optional(),
        /** Caption overrides: strictly capped by typography-routing spec
         *  (display_title ≤ 20 chars, display_attribution ≤ 32 chars). When
         *  absent, the renderer composes `ARTIST · YEAR` and renders `title`
         *  directly — both must already fit the caps, or ingestion rejects. */
        display_title: z.string().optional(),
        display_attribution: z.string().optional(),
        /** Optional pixel dimensions — when both provided, the gallery-visual
         *  template picks a layout class based on aspect ratio (bleed vs.
         *  matted pillarbox/letterbox). When absent, falls back to panel-
         *  native full-bleed. */
        pixel_width: z.number().optional(),
        pixel_height: z.number().optional(),
      })
      .optional(),
    text: z
      .object({
        form: form,
        body: z.string(),
        /** Parallel Japanese original for haiku/tanka, rendered in anthology
         *  style (original above the translation). Ignored on other forms. */
        body_ja: z.string().optional(),
        title: z.string().optional(),
        poet: z.string(),
        dates: z.string().optional(),
        language: z.enum(['en', 'ro']).default('en'),
      })
      .optional(),
    /** Summary face delight zone. Opposite modality from the Gallery hero:
     *  - flavor: visual → companion is text (short fragment/haiku/aphorism)
     *  - flavor: text   → companion is visual (small image with caption)
     *  Corresponds to the triplet's `summary` slot; see `corpus-triplets`. */
    companion: z
      .discriminatedUnion('kind', [
        z.object({
          kind: z.literal('visual'),
          image_path: z.string(),
          title: z.string().optional(),
          artist: z.string(),
          year: z.string().optional(),
        }),
        z.object({
          kind: z.literal('text'),
          form: form,
          body: z.string(),
          /** Parallel Japanese original for haiku/tanka; rendered alongside
           *  the translation in anthology style on the Summary delight. */
          body_ja: z.string().optional(),
          poet: z.string(),
          title: z.string().optional(),
          dates: z.string().optional(),
          language: z.enum(['en', 'ro']).default('en'),
        }),
      ])
      .optional(),
  }),
  night: z
    .object({
      image_path: z.string().optional(),
      title: z.string().optional(),
      fragment: z.string().optional(),
    })
    .optional(),
});

export const clockInput = z.object({
  time: z.string(), // HH:MM
  date: z.string(), // human-readable
});

export const SCHEMAS = {
  summary: z.object({
    clock: clockInput,
    weather: weatherInput,
    news: newsInput,
    pairing: pairingInput,
    sonos: sonosInput.optional(),
    device: deviceInput.optional(),
  }),
  weather: z.object({
    clock: clockInput,
    weather: weatherInput,
    device: deviceInput.optional(),
  }),
  gallery: z.object({
    clock: clockInput,
    pairing: pairingInput,
    device: deviceInput.optional(),
  }),
  night: z.object({
    clock: clockInput,
    weather: weatherInput,
    pairing: pairingInput,
    device: deviceInput.optional(),
  }),
  'now-playing': z.object({
    sonos: sonosInput,
    clock: clockInput,
    device: deviceInput.optional(),
  }),
} as const;

export type SummaryInput = z.infer<(typeof SCHEMAS)['summary']>;
export type WeatherModeInput = z.infer<(typeof SCHEMAS)['weather']>;
export type GalleryInput = z.infer<(typeof SCHEMAS)['gallery']>;
export type NightInput = z.infer<(typeof SCHEMAS)['night']>;
export type NowPlayingInput = z.infer<(typeof SCHEMAS)['now-playing']>;
