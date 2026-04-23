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

export function inputsDir(): string {
  return process.env.RENDERER_INPUTS_DIR ?? path.join(ROOT, 'inputs');
}

export const MODES = ['summary', 'weather', 'gallery', 'night', 'now-playing'] as const;
export type Mode = (typeof MODES)[number];

export function isMode(s: string): s is Mode {
  return (MODES as readonly string[]).includes(s);
}
