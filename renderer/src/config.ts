import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

export const ROOT = path.resolve(__dirname, '..');
export const TEMPLATES_DIR = path.join(ROOT, 'templates');
export const FONTS_DIR = path.join(TEMPLATES_DIR, 'fonts');
export const OUT_DIR = path.join(ROOT, 'out');

export const PORT = Number(process.env.RENDERER_PORT ?? 8575);
export const HOST = process.env.RENDERER_HOST ?? '0.0.0.0';

export const VIEWPORT = { width: 1200, height: 825 } as const;
// Revert to 1× native. 2× supersample + Lanczos looked better in the browser
// PNG preview but actually produced SOFTER output on the physical panel:
// server-side quantize + device-side dither was compounding. MagInkDash
// (proven crisp on hardware) uses a plain 1× screenshot; we match that.
export const DEVICE_SCALE_FACTOR: number = 1;

/**
 * Where Floyd-Steinberg error diffusion happens.
 *
 * - `server` — the renderer dithers within each mode's photo mask and emits
 *   palette-constrained output; firmware must draw with `dither=false`.
 * - `device` — the renderer emits full-range greyscale and the Inkplate
 *   library dithers on decode; firmware must draw with `dither=true`.
 *
 * The two must agree. Old firmware + `server` double-diffuses (smudge); new
 * firmware + `device` hard-truncates to 3 bits (banding). This is a switch
 * rather than a constant so rollback is a restart instead of an OTA cycle —
 * see `openspec/changes/move-dither-server-side/design.md` D4.
 *
 * Defaults to `device` until hardware validation confirms the server path.
 */
export type DitherPlacement = 'server' | 'device';

/**
 * Read per call, like `inputsDir()`, so tests can exercise both paths.
 *
 * Defaults to `server` since 2026-08-10, when the A/B probe confirmed on the
 * physical panel that the device-side dither renders washed out and ~2.7 s
 * slower per draw. See `firmware/docs/dither-hardware-validation.md`.
 * Set `RENDERER_DITHER=device` to fall back — but only alongside firmware
 * built with `dither=true`, or the panel bands.
 */
export function ditherPlacement(): DitherPlacement {
  return process.env.RENDERER_DITHER === 'device' ? 'device' : 'server';
}

export function inputsDir(): string {
  return process.env.RENDERER_INPUTS_DIR ?? path.join(ROOT, 'inputs');
}

export const MODES = ['summary', 'weather', 'gallery', 'night', 'now-playing'] as const;
export type Mode = (typeof MODES)[number];

export function isMode(s: string): s is Mode {
  return (MODES as readonly string[]).includes(s);
}
