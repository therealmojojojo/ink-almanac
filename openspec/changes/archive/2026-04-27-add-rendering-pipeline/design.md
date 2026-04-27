## Context

The renderer is the only place in the system where aesthetic quality gets decided. Every other capability is either plumbing (pairing, ingestion, firmware) or content (corpus, curation). Whether the dashboard feels like art or feels like a hobby project comes down to how this service behaves at the pixel level.

Three projects were studied before this change: MagInkDash (closest prior art, Inkplate 10 + OpenAI), sibbl/hass-lovelace-kindle-screensaver (most polished image-preparation chain in the space), and HomePlate (multi-mode "activities" pattern). The architecture here borrows from all three: MagInkDash's topology (server on Mac host, device as dumb PNG client), sibbl's image-prep chain (gamma removal → contrast → crush → quantize), and HomePlate's per-mode URL contract.

The surveys also ruled out two alternatives. ESPHome lambda rendering for 1200×825 utility zones is widely attempted and widely abandoned, and the Inkplate ESPHome component has open IO-expander issues. Direct Lovelace-screenshot as the primary mode produces generic-looking results that waste the 9.7" real estate. The "server renders the entire frame as a PNG" pattern is the converged state of the art, and this change adopts it wholesale.

## Goals / Non-Goals

**Goals:**
- Pixel-perfect, reproducible rendering of each mode at 1200×825 with Inkplate-palette quantization.
- Fast iteration loop: template edits are visible in a browser preview within seconds.
- Dither quality matching the best of the genre (sibbl-level image prep).
- Form-aware typography: poems look like the poems they are.
- Auto-start on host boot — no manual babysitting.

**Non-Goals:**
- Rendering on the device. The Inkplate is a dumb client.
- ESPHome integration at the rendering layer.
- Remote/cloud rendering. Everything runs on the Mac host.
- Lovelace screenshotting as a primary path. (It may live as an emergency fallback someday; not in this change.)
- Live data fetching beyond what inputs are passed in. The renderer is pure; data gathering belongs to `add-ha-integrations`.

## Decisions

### TypeScript/Node with Playwright

Rationale: Playwright's TS bindings are first-class and match the HTML-template iteration story. `sharp` is the fastest, most capable image-processing library in the Node ecosystem. The Mockup.html already uses CSS techniques (CSS variable `--u` scaling, Google Fonts via `@font-face`) that carry over directly. Python + Pillow + playwright-python would also work but lose the tight iteration story — for a rendering service that ships HTML, Node is the right habitat.

### Headless Chromium at deviceScaleFactor=1

Rationale: the Inkplate is a 1:1 device. We render at the target resolution directly, not at 2x and downsample. This avoids blurring text edges, preserves the hand-placed pixel boundaries in mono-caps chrome, and makes every pixel in the preview identical to what the panel sees.

### Hybrid dither policy: image zones only

Pictorial content benefits from dithering (tones, gradients, subtle detail). UI content loses from it (sharp black-on-paper text becomes noisy). The policy encodes this: pictorial zones get Floyd-Steinberg with palette awareness, UI zones get direct quantization with hard edges. This matches what humans perceive as "intentional" on e-paper.

Alternative considered: dither everything. Rejected because sibbl-style pure greyscale UI looks strictly better than dithered UI on text-heavy content.

Alternative considered: dither nothing. Rejected because photographs and paintings with smooth tones band severely against 8 levels.

### Image-prep chain copied from sibbl

Sibbl/hass-lovelace-kindle-screensaver's chain (gamma remove → contrast → crush → quantize) is the most mature prep code in the space and produces visibly better greyscale output than naive conversions. We re-implement it against `sharp` rather than depend on sibbl's code directly, but the steps and thresholds follow their proven sequence.

### No caching

Peak request rate is trivial — scheduled Inkplate wakes at 15-minute intervals during active hours plus PIR wakes bounded by a 5-minute cooldown. A single Playwright instance rendering in 200–500 ms comfortably covers that without caching. Skipping the cache removes an entire class of bugs (stale hits from under-hashed inputs, invalidation on font/template changes, memory growth over long uptime) and keeps the renderer pure at its interface: identical inputs always re-execute and always produce identical output.

Reproducibility is still a spec requirement, just satisfied by determinism rather than memoization.

### Inputs contract as typed schemas, per mode

Each mode declares a Zod (or equivalent) input schema. The renderer validates at the boundary; templates only see well-typed inputs. Rationale: the boundary is where things go wrong (HA sends a null, the Sonos entity is unavailable, the pairing file is missing). Failing explicitly at the boundary with a useful error is vastly better than templates rendering garbage.

### Truncation at the renderer, not the template

The Content producer contract from `requirements/Requirements.md` says "HA truncates; the renderer draws literally." We keep this contract but shift the truncation responsibility: HA can truncate upstream if it wants (fast signal, prevents over-the-wire bloat), but the renderer enforces the budget as a final line of defense, so the template absolutely cannot overflow its zone even if upstream fails. This is belt-and-suspenders but it's cheap and prevents catastrophic layout failures.

### Typography routing by `form` field

The "no Ozymandias in italics" rule is encoded in `form` dispatch: `sonnet` and `free-verse` go roman; `haiku` and `fragment` go italic; aphorism and quote take their appropriate treatments. The taxonomy owns the `form` values; the renderer owns their typographic consequences. Clear separation.

### Snapshot tests as regression gate

Visual output is what matters; CSS unit tests cannot catch "the clock overlapped the forecast after this change." Playwright snapshot tests against golden PNGs are the only honest way to ensure no mode breaks silently. The threshold is configurable so intentional changes can be approved by updating goldens deliberately.

### Auto-start via launchd user agent

The renderer must be available to HAOS and the Inkplate without manual intervention. A launchd user agent starts it at login (or boot, depending on plist configuration). `pm2` or `forever` are plausible alternatives but launchd is native, transparent, and requires no additional runtime.

## Risks / Trade-offs

- **Chromium memory footprint on the Mac host.** Playwright/Chromium can idle at 200–400 MB. Mitigation: runs as a long-lived service (amortizes startup), pages reuse the same browser context across modes, one browser instance handles all requests.

- **Font rendering differences between macOS Chromium and the "final" rendered output.** If the same template is rendered on two different hosts, minor anti-aliasing differences appear. Mitigation: deviceScaleFactor=1 and explicit font rendering settings pin the output; snapshot tests catch host drift.

- **Dither speed for large images.** Floyd-Steinberg on a 1200×825 image is a few ms in native code, negligible. Not a risk; noted for completeness.

- **Template drift from Mockup.html.** The Mockup.html reference uses one set of conventions; the templates will evolve. Mitigation: the specs codify the palette, families, size floor, and form rules — the non-negotiables — while leaving layout details to iteration.

- **Playwright version lock.** Chromium rendering is deterministic only within a major version; a Playwright update may shift golden snapshots. Mitigation: pin Playwright version in `package.json`, update deliberately, re-bake goldens under change-proposal discipline.

- **Truncation ambiguity.** Truncating a Romanian compound word with an ellipsis can be ugly. Mitigation: budgets are tuned during template building; the content-producer contract says HA may pre-truncate more elegantly (at word boundaries) upstream; the renderer's truncation is a last-resort safety net, not the primary UX.

## Migration Plan

Greenfield. No prior rendering exists. On apply:

1. Scaffold `renderer/` with package.json, tsconfig, directory layout.
2. Implement HTTP server with `/healthz` and stubbed mode endpoints returning blank PNGs.
3. Implement Playwright-based rendering for a single mode (Summary) end-to-end, including input schema and template.
4. Implement the image-prep chain and palette quantization.
5. Implement dither for image zones.
6. Implement snapshot tests.
7. Extend to remaining modes in a predictable order (Weather, Gallery visual-day, Gallery text-day, Night, Now-Playing).
8. Install launchd user agent.
9. Write dither test harness.

Rollback: stop the service, remove `renderer/`. No data anywhere else depends on it yet (the firmware and HA integrations that call it haven't shipped).

## Open Questions

1. **HTTP framework.** `hono` (lean, fast, modern) vs `fastify` (mature, plugin-rich). Probably `hono` given we have no plugin needs. Deferred to implementation.

2. **Font caching strategy.** Self-host Fraunces + Plex files in `renderer/templates/fonts/`, or rely on Google Fonts at first-render and warm the Chromium disk cache? Probably self-host for reproducibility. Deferred.

3. **How to handle Now-Playing album art that's remote (Spotify CDN URL)?** Fetching at render time adds latency and fails when offline. Probably download-on-track-change via HA automation, pass local path to the renderer. Coordinated with `add-ha-integrations`.

4. **Should the dither test be a gated step in CI or a manual command?** Leaning manual — it produces a long document with inline images, better reviewed by a human than auto-enforced. Defer.

5. **Preview endpoint auth.** The renderer listens on LAN. Preview HTML pages are harmless but include Gallery content that could include personal-library items. Probably no auth needed for LAN-only operation; document the assumption. Revisit if the deployment topology ever changes.
