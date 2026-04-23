# Inkplate renderer

Server-side rendering pipeline. HTML templates + Playwright + `sharp` image-prep + palette-aware Floyd-Steinberg → Inkplate-palette PNGs at 1200×825.

## Setup

```bash
cd renderer
npm install
npx playwright install chromium
# drop font files into templates/fonts/ (see that directory's README)
```

## Run

```bash
npm run dev            # watch mode on port 8575
npm start              # one-shot
npm run build          # TypeScript check
npm run verify         # lint templates + zones + fonts
npm test               # snapshot tests (seeds goldens on first run)
npm run dither-test    # writes ../docs/dither-test-results.md
```

## Endpoints

| Path | Purpose |
| ---- | ------- |
| `GET /healthz` | 200 + `{status, playwright_ready}` |
| `GET /display/{mode}.png` | Rendered PNG at 1200×825, Inkplate palette |
| `GET /display/{mode}/preview` | Human-facing HTML preview |
| `POST /inputs/:name` | Atomic write of an input JSON file (HA publisher target) |
| `GET /dither-test` | In-browser harness viewer |
| `GET /static/...` | CSS and self-hosted fonts |
| `GET /inputs/{file}` | Input JSON files (used by templates for images, etc.) |

Modes: `summary`, `weather`, `gallery`, `night`, `now-playing`.

## Inputs

By default the renderer reads JSON from `renderer/inputs/`. Override with
`RENDERER_INPUTS_DIR=/path/to/inputs`. Missing required inputs return 503,
with one exception: `device.json` is optional on every face — when absent
the battery indicator falls back to its graceful-degradation em-dash per
the `dashboard-faces` spec.

Per mode:

- `summary` ← `clock, weather, climate, hn, pairing, device` (sonos optional)
- `weather` ← `clock, weather, device`
- `gallery` ← `clock, pairing, device`
- `night` ← `clock, weather, pairing, device`
- `now-playing` ← `clock, sonos, device`

See `src/modes/schema.ts` for the Zod contracts.

### `POST /inputs/:name`

HA publishes each renderer input by POSTing its JSON body to this endpoint.

- **Auth**: `Authorization: Bearer $RENDERER_INPUT_TOKEN`. Missing header → 401, mismatch → 403.
- **Allow-list**: `clock | weather | climate | hn | pairing | sonos | device`. Others → 404.
- **Body limit**: 256 KB. Oversize → 413.
- **Write semantics**: temp-file + atomic rename into `RENDERER_INPUTS_DIR`. Success → 204 No Content.
- **Schema validation**: the renderer does NOT validate body shape at POST time. Shape errors surface at the next `/display/*.png` fetch as a 400 from the Zod parser.

Set `RENDERER_INPUT_TOKEN` in the renderer's environment (e.g., launchd plist).
On the HA side, store `"Bearer <token>"` as `renderer_input_auth_header` in
`secrets.yaml` — `!secret` drops it directly into the Authorization header.
See `ha/docs/architecture.md` for the publisher catalog and triggers.

## Image pipeline

Playwright captures at CSS viewport 1200×825 with `deviceScaleFactor=1`. The
screenshot goes through `sharp.greyscale()` and out as an 8-bit greyscale PNG.
That's the whole pipeline.

The device's Inkplate library runs its own Floyd-Steinberg dither onto the
8-shade panel palette during `drawImage(url, ..., dither=true)`. Any server-
side palette manipulation compounds with that dither pass and produces
visible smudge on the physical panel (we tested this — see the
`improve-text-crispness` openspec change for the hardware-validated rationale
and the recorded dead end that led here).

Photo-heavy modes (currently Gallery, possibly Night) will eventually need a
targeted server-side palette-mapping step because their full-greyscale PNGs
overflow the device's pngle decoder memory budget. That's tracked as a
follow-up — see `renderer/src/image/prep.ts`, which is retained but currently
unused for this reason.

Dither policy per mode lives in `src/modes/{mode}.ts:ditherMask()`.

## Typography

Three families only: Fraunces, IBM Plex Mono, IBM Plex Sans. Form dispatch in
`src/typography.ts`. "No Ozymandias in italics" is encoded:
sonnet/free-verse/stanzaic/prose-poem/quote → Fraunces Regular;
haiku/tanka/fragment/aphorism → Fraunces Italic.

## Zone budgets

Source: `openspec/specs/dashboard-faces/spec.md`. Transcribed in `src/zones.ts`.
`npm run check-zones` fails the build on divergence once that spec is archived.

Prose zones → hard-truncate + `…`. Verse zones → 422 with `zone` + `inputLength`.
Length is measured in extended grapheme clusters (UAX #29).

## Launchd auto-start

```bash
# edit the path inside the plist, then:
cp renderer/launchd/com.inkplate.renderer.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.inkplate.renderer.plist

# verify
curl http://127.0.0.1:8575/healthz
```

The service restarts on crash (`KeepAlive`), throttled to 10s. Logs go to
`/tmp/inkplate-renderer.{out,err}.log`.

## Snapshot tests

`npm test` renders every mode against `test/fixtures/*.json` and compares to
`test/__golden__/{mode}.png`. Diffs over 5 pixels fail. First run seeds the
goldens. Re-seed deliberately with `UPDATE_GOLDENS=1 npm test`.
