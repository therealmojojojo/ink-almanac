## Why

First render on physical hardware (Inkplate 10 v2, 8-shade panel) showed text with smudged, soft-edged glyphs — worse than the reference PNG looks in a browser. Two successive hypotheses were tested on hardware:

1. **First hypothesis (wrong):** supersample at 2× in Chromium, Lanczos-downsample to 1200×825, loosen the contrast crush (0.05/0.95 → 0.10/0.90). Practitioner consensus for e-paper. **Result on device: no visible improvement; text still smudged.**
2. **Second hypothesis (correct):** the smudge comes from double-processing — server-side palette-quantization followed by device-side Floyd-Steinberg dither on the already-quantized PNG. Adopt the MagInkDash pipeline (the only native-Inkplate-10 reference we had) which is plain `Chromium screenshot → PNG → device dithers once`. **Result on device: visibly crisp.**

This change ratifies hypothesis 2. The supersample / Lanczos / crush detour is kept in the design doc as a recorded dead end, because the finding (the panel cannot tolerate server-side palette steps when the library is going to re-dither) is load-bearing for any future pipeline work.

## What Changes

- Rendering engine: Playwright `deviceScaleFactor` stays at `1`. Viewport 1200×825. Screenshot goes directly from Chromium to a single-channel 8-bit greyscale PNG via `sharp.greyscale()` — no supersample, no Lanczos downsample.
- Image-preparation chain: replaced. The prior chain (linearize → contrast → crush → dither → quantize → re-encode) is removed from the `/display/:mode.png` path. The device's Inkplate library handles greyscale → 8-palette mapping via its own Floyd-Steinberg pass, which is what it was designed to do when the source image is 8-bit greyscale (v. MagInkDash).
- Selective-dithering scenario: revised. Server-side Floyd-Steinberg is no longer performed on any zone in the default path. The distinction between "pictorial" and "UI" zones is no longer meaningful at the pipeline level (all zones are rendered the same way). If photo-heavy modes later need server-side palette mapping to fit PNG size under the device's ~1 MB download budget, we'll reintroduce it as a targeted step, not as a default.
- `renderer/src/image/prep.ts`: retained but orphaned. The module still compiles and its functions are still tested in isolation for when photo-mode quantization lands; no runtime code path calls `prepare()`.
- **Expected cost:** per-mode render time drops (no Lanczos pass, no per-pixel float loop). Output PNG size rises for photo-heavy modes (8-bit greyscale, not 3-bit palette) — confirmed on hardware that Gallery mode at 914 KB overflows the library's decoder; tracked as a follow-up.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `rendering-pipeline`: revises the Rendering engine, Image-preparation chain, and Selective dithering requirements.

## Impact

- **Code**: `renderer/src/config.ts` (`DEVICE_SCALE_FACTOR: 2 → 1`), `renderer/src/render.ts` (drop Lanczos + `prepare()` call, emit greyscale PNG directly). `renderer/src/image/prep.ts` becomes unreferenced from the hot path but is not deleted — it will be wanted again when photo-mode quantization lands.
- **Snapshot tests** (`renderer/test/__golden__/*.png`): goldens need re-seeding via `UPDATE_GOLDENS=1 npm test`. Visual change by design.
- **Palette-invariant test** (`renderer/test/snapshot.test.ts`): this test asserts that every pixel in `/display/summary.png` lands on the 8-shade Inkplate palette. That assertion is no longer true for the default path (output is full-greyscale PNG), and the test needs to be removed or scoped to a future photo-quantized mode.
- **Device firmware**: no change. The device's Inkplate library already dithers any greyscale PNG it fetches; it accepted our old quantized PNG and accepts the new greyscale PNG equally.
- **Known gap — Gallery mode**: 914 KB greyscale PNG overflows the Soldered Inkplate library's pngle decode path. Temporarily excluded from the firmware smoketest's cycling list. Needs a targeted quantize step for photo zones, tracked as a separate follow-up change.
- **Follow-ups the user requested but are out of scope here**: fridge-distance size bump + content redesign per mode (minimum legible font sizes at 1.5–2 m viewing distance). That's a `redesign-for-fridge-distance` change against `dashboard-faces`, not against `rendering-pipeline`.
