## 1. Pipeline simplification

- [x] 1.1 Set `DEVICE_SCALE_FACTOR` in `renderer/src/config.ts` back to `1`
- [x] 1.2 In `renderer/src/render.ts`, drop the Lanczos downsample step and the `prepare()` call; return `sharp(screenshot).greyscale().png().toBuffer()` directly
- [x] 1.3 Leave `renderer/src/image/prep.ts` in place (orphaned; reused when photo-mode quantization lands); mark its orphan status in a header comment

## 2. Validate on real hardware

- [x] 2.1 A/B the MagInkDash native 1200×825 render against our output on the physical panel; confirm both show crisp text (control: the only proven-crisp reference)
- [x] 2.2 Render weather, summary, night, now-playing with the new pipeline and confirm device-side fetch + draw + visual crispness on the panel
- [ ] 2.3 Fix Gallery mode: 914 KB greyscale PNG overflows pngle on-device. Needs a follow-up change introducing server-side palette quantization scoped to photo zones, with `dither=false` in firmware for those modes

## 3. Tests

- [ ] 3.1 Re-seed snapshot goldens via `UPDATE_GOLDENS=1 npm test` to reflect the new output
- [ ] 3.2 Remove the palette-invariant assertion in `renderer/test/snapshot.test.ts` (no zone guarantees palette-only output in the default path) or scope it to a future photo-quantized mode
- [ ] 3.3 `npm run build` + `npm run verify` pass

## 4. Documentation

- [x] 4.1 Update `renderer/README.md` "Image pipeline" section to describe the new simple flow (Chromium → greyscale → PNG)
- [x] 4.2 Add a header comment to `renderer/src/image/prep.ts` noting the module is orphaned pending the photo-mode follow-up
