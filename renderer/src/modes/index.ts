import { z } from 'zod';
import type { DitherMask } from '../image/dither.js';
import { requireInput, loadInput, MissingInputError } from '../inputs.js';
import type { Mode } from '../config.js';
import { SCHEMAS } from './schema.js';
import * as summary from './summary.js';
import * as weather from './weather.js';
import * as gallery from './gallery.js';
import * as night from './night.js';
import * as nowPlaying from './nowPlaying.js';

export interface ModePrepared {
  html: string;
  dither: boolean | DitherMask;
}

async function gatherSummary(): Promise<unknown> {
  return {
    clock: await requireInput('clock'),
    weather: await requireInput('weather'),
    hn: await requireInput('hn'),
    pairing: await requireInput('pairing'),
    sonos: await loadInput('sonos'),
    device: await loadInput('device'),
  };
}

async function gatherWeather(): Promise<unknown> {
  return {
    clock: await requireInput('clock'),
    weather: await requireInput('weather'),
    device: await loadInput('device'),
  };
}

async function gatherGallery(): Promise<unknown> {
  return {
    clock: await requireInput('clock'),
    pairing: await requireInput('pairing'),
    device: await loadInput('device'),
  };
}

async function gatherNight(): Promise<unknown> {
  return {
    clock: await requireInput('clock'),
    weather: await requireInput('weather'),
    pairing: await requireInput('pairing'),
    device: await loadInput('device'),
  };
}

async function gatherNowPlaying(): Promise<unknown> {
  return {
    clock: await requireInput('clock'),
    sonos: await requireInput('sonos'),
    device: await loadInput('device'),
  };
}

export interface PrepareOptions {
  /** Summary layout variant: 'a' | 'b' | 'c'. Ignored by other modes. */
  variant?: string | undefined;
}

export async function prepareMode(
  mode: Mode,
  opts: PrepareOptions = {},
): Promise<ModePrepared> {
  switch (mode) {
    case 'summary': {
      const raw = await gatherSummary();
      const input = SCHEMAS.summary.parse(raw);
      const variant: summary.SummaryVariant =
        opts.variant === 'b' || opts.variant === 'c' ? opts.variant : 'a';
      return {
        html: summary.buildHtml(input, variant),
        dither: summary.ditherMask(input),
      };
    }
    case 'weather': {
      const raw = await gatherWeather();
      const input = SCHEMAS.weather.parse(raw);
      return { html: weather.buildHtml(input), dither: weather.ditherMask() };
    }
    case 'gallery': {
      const raw = await gatherGallery();
      const input = SCHEMAS.gallery.parse(raw);
      return { html: gallery.buildHtml(input), dither: gallery.ditherMask(input) };
    }
    case 'night': {
      const raw = await gatherNight();
      const input = SCHEMAS.night.parse(raw);
      return { html: night.buildHtml(input), dither: night.ditherMask(input) };
    }
    case 'now-playing': {
      const raw = await gatherNowPlaying();
      const input = SCHEMAS['now-playing'].parse(raw);
      return { html: nowPlaying.buildHtml(input), dither: nowPlaying.ditherMask(input) };
    }
  }
}

export { MissingInputError };
export { z };
