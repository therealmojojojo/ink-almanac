## Why

The Inkplate 10 is a thin client: it fetches PNGs at 1200×825 and draws them. Something has to produce those PNGs with typography, layout, and dithering quality that make the frame feel intentional rather than hobbyist. That "something" is the rendering pipeline — the server-side engine that turns HTML templates plus live data into properly processed greyscale PNGs, one per mode. Without it, every other capability is abstract.

The state-of-the-art survey (MagInkDash, sibbl/hass-lovelace-kindle-screensaver, HomePlate, TRMNL's Terminus) converges on this architecture: headless browser renders HTML/CSS, image-processing chain prepares the output, dither only where it helps. This change ratifies that pattern as the project's approach and defines the renderer's contract with its consumers.

## What Changes

- Introduce a Node/TypeScript service under `renderer/` that runs on the Mac host (not inside the HAOS VM).
- Use **Playwright** (Chromium) for HTML→PNG rendering at an exact device pixel ratio of 1:1, output size 1200×825.
- Implement the **image-preparation chain** (modeled after sibbl/hass-lovelace-kindle-screensaver): gamma removal, contrast boost, saturation zero, black/white crush, applied via `sharp`.
- Implement **palette-aware Floyd-Steinberg dithering** against the Inkplate 10's 3-bit greyscale palette `[0, 36, 73, 109, 146, 182, 219, 255]`. Applied **only** to pictorial image zones (Gallery visual-day, Night nocturne, Now-Playing album art). UI-heavy modes (Summary, Weather, Gallery text-day) are rendered without dither for sharpness.
- Expose an HTTP API with `GET /display/{mode}.png` endpoints; the Inkplate firmware becomes a dumb client of this interface.
- Support a `GET /display/{mode}/preview` HTML endpoint for in-browser development so the operator can iterate on templates visually.
- Implement a **template-level contract** for per-mode data inputs. The renderer receives data from HA (weather, climate, Sonos, HN, today's pairing JSON); templates consume typed inputs, with character budgets enforced at the renderer boundary.
- Implement **per-form typography routing** for text-day Gallery: `form: haiku` uses italic Fraunces opsz 72; `form: sonnet` and `form: free-verse` use roman Fraunces opsz 72 (per the "no Ozymandias in italics" rule); `form: aphorism` and `form: fragment` may use italic; `form: quote` uses roman with opening em-dash flourish.
- Implement **visual snapshot testing** via Playwright so template changes cannot silently break any mode.
- Implement a **six-image dither test harness** producing the test output required by `requirements/Requirements.md` (per-category render of strong and weak categories, written to `docs/dither-test-results.md`).

## Capabilities

### New Capabilities

- `rendering-pipeline`: The server that renders mode-specific PNGs from HTML templates and data, including the image-preparation chain, palette-aware dithering for image zones, HTTP API, and development preview.
- `typography-routing`: The rules that map corpus `form` values to concrete Fraunces axes (regular vs italic, opsz value, size, em-dash flourish, margin) so text-day Gallery output matches the form of the text.

### Modified Capabilities

None. This change introduces new capabilities only; nothing pre-exists.

## Impact

- **New TypeScript project** under `renderer/` with `package.json`, `tsconfig.json`, templates, source.
- **New runtime dependencies**: `playwright`, `sharp`, an HTTP framework (`hono` or `fastify` — TBD at apply time), `zod` for input validation, `pino` for logging.
- **New dev dependencies**: Playwright for snapshot testing, Vitest or similar runner.
- **New LAN service**: the renderer listens on a configurable port (default 8575) on the Mac host, reachable from HAOS and the Inkplate.
- **Bootstrap auto-start**: documented launchd plist so the renderer starts when the Mac host boots; implementation of the plist is a task under this change.
- **Consumes but does not modify**: `corpus/` (reads sidecars and binaries for Gallery/Night/Now-Playing content), `pairings/{date}.json` (reads today's pairing), HA REST API or local state files (reads live data). No writes to any of these.
- **Future hooks**: exposes the HTTP endpoints that `add-device-firmware` and `add-ha-integrations` will call. Those changes bind to the endpoint contract ratified here.
