## 1. Verify mask geometry against current layouts

- [x] 1.1 Add a debug endpoint or test that overlays a mode's `ditherMask()` onto its rendered PNG, so mask rectangles can be checked visually rather than read from source
- [x] 1.2 Verify `gallery.ts:212` split-layout mask right edge matches the CSS image-column width (`--gv-img-width`) within 2 px, for a portrait and a square image
- [x] 1.3 Verify the Gallery landscape path: the caption band is 108 px (`gallery-visual.css:14`), not the 72 px its comment claims — confirm no mask pixel enters the band
- [x] 1.4 Verify `night.ts:137` nocturne mask (`x 576–1200`) against the actual `night.css` grid columns
- [x] 1.5 Verify `summary.ts:337-340` delight-cell mask (`x 48–650, y 500–770`) against the current summary layout
- [x] 1.6 Verify `nowPlaying.ts:112-115` album-art mask (left 825 columns) against the current now-playing layout
- [x] 1.7 Correct any mask whose rectangle has drifted; add a unit test pinning each mask to its layout-derived geometry

## 2. Renderer: server-side dithering

- [x] 2.1 Add `RENDERER_DITHER` to `config.ts` (`'server' | 'device'`, default `'device'`); log the effective mode once at startup
- [x] 2.2 In `render.ts`, stop discarding the `dither` parameter — when mode is `server`, apply `floydSteinberg()` from `image/dither.ts` with the mode's mask; when `device`, preserve current behavior
- [x] 2.3 Switch the greyscale step to `sharp.toColourspace('b-w')` so output is genuinely single-channel (currently RGB with three identical channels)
- [x] 2.4 Call `assertPaletteOnly()` on the result in `server` mode and fail the render loudly if it trips
- [x] 2.5 Confirm no tonal manipulation is introduced — no linearize, contrast, or crush; `prep.ts` stays uncalled
- [x] 2.6 Verify `/display/{mode}.png` byte-for-byte reproducibility holds in both modes

## 3. Renderer: tests

- [x] 3.1 Invert existing tests that assert full 0–255 range output — under `server` mode they must assert palette membership
- [x] 3.2 Add a test that a Weather face (`ditherMask()` returns `false`) is entirely hard-quantized with no diffusion
- [x] 3.3 Add a test that a Gallery photo region's blurred mean tracks the pre-quantization greyscale mean within 3/255 — this is the regression guard for the brightness bias that motivated the change
- [x] 3.4 Add a test that a text zone outside the mask carries a single flat palette value, not a mixture
- [x] 3.5 Add a test asserting output metadata reports `channels: 1`
- [x] 3.6 Confirm the full renderer suite passes in both `RENDERER_DITHER` modes

## 4. Firmware

- [x] 4.1 Change `RealDisplay::drawImageFromUrl` (`firmware/src/hal/real/RealDisplay.h:31`) to pass `dither=false`; replace the stale comment about the library's dither with the palette-maps-1:1 rationale
- [x] 4.2 Check `smoketest.cpp:72`, which passes `dither=true` on its own call path, and decide whether it follows or stays as a library-behavior probe
- [x] 4.3 Confirm no mock or host-side test asserts `dither=true`
- [x] 4.4 Build for `inkplate10` and confirm no size regression

## 5. Hardware validation (gates the default flip)

- [x] 5.1 Render one Gallery visual-day face under `RENDERER_DITHER=device` and under `server`; keep both PNGs
- [x] 5.2 Flash firmware with `dither=false`; display both PNGs on the panel and photograph each under identical lighting
- [x] 5.3 Compare: confirm the server-side version is not brighter than intended and shows more retained detail — the simulation predicts RMSE 19.97 → ~2.7 and brightness bias +19 → ~0
- [x] 5.4 Judge R3 on hardware: paper `#ececec` (236) hard-quantizes to palette 219 rather than being pushed to 255 by the library bug. If faces read flat, change `--paper` to `#ffffff` in `tokens.css` so it lands on level 7 deliberately
- [ ] 5.5 N/A for now — sRGB-space was good enough on hardware that the linear-light comparison was not run. Open question stands; see `firmware/docs/dither-hardware-validation.md`
- [x] 5.6 Record findings in `firmware/docs/` alongside the existing panel notes; if hardware contradicts the simulation, stop and revise rather than shipping

## 6. Rollout

- [x] 6.1 OTA the firmware with `dither=false` while the renderer is still in `device` mode; confirm the panel bands visibly (the expected transient)
- [x] 6.2 Set `RENDERER_DITHER=server` and restart the renderer; confirm the panel renders correctly
- [~] 6.3 PARTIAL: Gallery verified on hardware end-to-end; all five faces verified palette-only server-side. A natural rotation spans the day — observe one full rotation — Summary, Weather, Gallery, Night, Now-Playing — checking each face for banding at mask boundaries and speckle in text
- [ ] 6.4 BLOCKED until evening (Night mode is time-of-day gated). Verify the Night 1-bit partial-update path still behaves: the cold-state over-paint assumes what the 3-bit PNG left in the phrase zone, and those pixel values have changed
- [x] 6.5 Confirm the per-wake download drop (702 KB → ~537 KB measured on the Gallery face)
- [ ] 6.6 Test the rollback path once: set `RENDERER_DITHER=device`, restart, confirm banded-but-legible output, then restore

## 7. Settle

- [x] 7.1 Flip the `RENDERER_DITHER` default to `server`
- [ ] 7.2 Remove the env var and make server-side dithering unconditional
- [ ] 7.3 Delete `renderer/src/image/prep.ts` — orphaned since `improve-text-crispness`, and this change supersedes its stated future purpose
- [ ] 7.4 Update `renderer/README.md` and `CLAUDE.md` if either describes the device as the dithering stage
- [ ] 7.5 Run `openspec validate move-dither-server-side` and archive

## 8. Panel level calibration (added 2026-08-10, from hardware findings)

- [x] 8.1 Build a step-wedge target with mirrored level positions and corner registration marks
- [x] 8.2 Add `DITHER_AB_WEDGE` probe mode with ghost-clear flush before the measured draw
- [x] 8.3 Measure level response from two independent photographs (agree to 6.0/255)
- [x] 8.4 Split `INKPLATE_PALETTE` into selector bytes + `PANEL_APPEARANCE`; quantize and diffuse in appearance space
- [x] 8.5 Update tests to compare in appearance space rather than raw byte values
- [x] 8.6 Reflashed `inkplate10`; panel restored to normal service on the calibrated path
- [x] 8.7 Operator judged the calibrated palette WORSE (detail loss); reverted. Measured values kept as `PANEL_APPEARANCE_MEASURED`, unused

## 9. Blue-noise dither for photo zones (added 2026-08-10, from operator judgement)

- [x] 9.1 Decompose residual error: dither texture +32..+45 vs resampling +0.8..+11.4
- [x] 9.2 Add `bake:blue-noise` void-and-cluster generator; verify 68:1 blue spectrum
- [x] 9.3 Measure FS vs blue noise across perceptual blur radii — blue noise wins 4/4 at viewing distance
- [x] 9.4 Ship `blueNoiseDither` on the masked photo path; keep `floydSteinberg` for comparison
- [x] 9.5 Tests: mean-tone preservation, bracketing levels, matrix permutation
- [x] 9.6 Deploy to production renderer; panel restored to real firmware
- [ ] 9.7 Update the `rendering-pipeline` spec delta, which still specifies Floyd–Steinberg
