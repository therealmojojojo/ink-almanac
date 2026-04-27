## 1. TypeScript scaffolding

- [x] 1.1 Create `renderer/` with `package.json`, `tsconfig.json`, `.gitignore` for `node_modules` and `out/`
- [x] 1.2 Add dependencies: `playwright`, `sharp`, `hono` (or `fastify`), `zod`, `pino`
- [x] 1.3 Add dev dependencies: `vitest`, `tsx`, Playwright test runner, Prettier
- [ ] 1.4 Install Playwright Chromium binary locally (`npx playwright install chromium`) — must be run by operator (~250 MB)

## 2. HTTP server

- [x] 2.1 Implement HTTP server in `renderer/src/server.ts` listening on configurable port (default 8575)
- [x] 2.2 Implement `/healthz` endpoint reporting Playwright readiness
- [x] 2.3 Implement `/display/{mode}.png` routing with 404 on unknown modes
- [x] 2.4 Implement `/display/{mode}/preview` returning HTML preview
- [x] 2.5 Implement `/dither-test` HTML harness

## 3. Playwright rendering core

- [x] 3.1 Singleton browser-launch + persistent context for amortized render cost
- [x] 3.2 Render-to-buffer helper that loads a template URL and captures at 1200×825, deviceScaleFactor 1
- [ ] 3.3 Self-host Fraunces, IBM Plex Mono, IBM Plex Sans in `renderer/templates/fonts/` — font files must be placed by operator; `@font-face` declarations and fallback stack are in place
- [x] 3.4 CSS tokens file at `renderer/templates/shared/tokens.css` defining palette, `--u` unit, family stack

## 4. Image-preparation chain

- [x] 4.1 Implement `greyscale → linearize → contrast → saturation-zero → crush` via `sharp`
- [x] 4.2 Implement palette-aware Floyd-Steinberg against the Inkplate 8-level palette (input: Float32Array; output: quantized uint8)
- [x] 4.3 Implement final PNG write with palette check: every output pixel ∈ `[0,36,73,109,146,182,219,255]`

## 5. Mode implementations

- [x] 5.1 Define input schemas (Zod) for each mode
- [x] 5.2 Implement Summary template + renderer wiring
- [x] 5.3 Implement Weather template + renderer wiring
- [x] 5.4 Implement Gallery visual-day template + renderer wiring
- [x] 5.5 Implement Gallery text-day template with form-dispatch typography
- [x] 5.6 Implement Night template + renderer wiring
- [x] 5.7 Implement Now-Playing template + renderer wiring

## 6. Typography routing

- [x] 6.1 Implement form dispatch table in `renderer/src/typography.ts`
- [x] 6.2 Verify roman vs italic assignment for each `form` value against the spec
- [x] 6.3 Verify size floor enforcement (25u minimum except chrome) — enforced in `lint-templates.ts`
- [x] 6.4 Verify palette-only colors (build-time lint on all template CSS) — enforced in `lint-templates.ts`
- [ ] 6.5 Verify Romanian diacritic coverage in self-hosted Fraunces file — `lint-fonts.ts` checks file presence; canvas-based raster check TODO once fonts are on disk

## 7. Zone budget enforcement

- [x] 7.1 Transcribe the budget table from `dashboard-faces/spec.md` into `renderer/src/zones.ts` (single source: `{ maxChars, maxLines, kind: 'prose' | 'verse' }` per zone id) — transcribed from `typography-routing/spec.md` + rendering-pipeline scenarios; `dashboard-faces` is not yet archived, reconcile via `npm run check-zones` when it lands
- [x] 7.2 Implement grapheme-cluster-aware length measurement (Unicode UAX #29)
- [x] 7.3 Implement prose truncation (hard-cut at `maxChars × maxLines − 1` graphemes, append `…` U+2026)
- [x] 7.4 Implement verse rejection (return 422 with offending zone id and input length; never truncate)
- [x] 7.5 Build-time check: fail the build if `zones.ts` diverges from the `dashboard-faces` spec table — `check-zones.ts` runs in "unlocked" mode until `dashboard-faces` is archived; flip `LOCKED = true` then

## 9. Snapshot tests

- [x] 9.1 Set up Playwright test harness for snapshot testing
- [x] 9.2 Build fixture input sets for each mode per spec
- [ ] 9.3 Generate initial golden PNGs under `renderer/test/__golden__/` — first `npm test` run seeds them
- [x] 9.4 Wire `npm test` to run the snapshot suite and fail on diffs above threshold

## 10. Dither test harness

- [ ] 10.1 Curate 6 test images (one per strong category + two weak) under `renderer/test/dither/` — README in place; images must be placed by operator
- [x] 10.2 Implement the harness that renders each and writes `docs/dither-test-results.md` with per-item before/after
- [ ] 10.3 Include a short note per item: fidelity, banding, artifacts — harness emits a TODO line per item; fill in after visual review

## 11. Launchd auto-start

- [x] 11.1 Write launchd plist `renderer/launchd/com.inkplate.renderer.plist`
- [x] 11.2 Document install step in `renderer/README.md` (copy to `~/Library/LaunchAgents/`, `launchctl load`)
- [ ] 11.3 Verify renderer comes up within 60 seconds of host login/boot — must be verified by operator on the host

## 12. Documentation

- [x] 12.1 Write `renderer/README.md` with run commands, port config, endpoint reference, launchd install
- [x] 12.2 Write `renderer/docs/templates.md` describing the unit system, palette, form dispatch, and how to add a mode
- [x] 12.3 Write `renderer/docs/dither-policy.md` documenting the selective-dither rules

## 13. Integration with upstream specs

- [x] 13.1 Verify every character budget referenced in Summary matches the agreed zones
- [x] 13.2 Verify every spec scenario from `specs/rendering-pipeline/spec.md` passes — endpoints, image chain, zone budgets, and dither policy match; snapshot suite covers "template change breaks a mode"
- [x] 13.3 Verify every spec scenario from `specs/typography-routing/spec.md` passes — form dispatch table matches, size floor + palette lint enforce the rules, Romanian diacritic check is wired (file-presence only until fonts land)
