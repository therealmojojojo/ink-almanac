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
npm run dev              # watch mode on port 8575
npm start                # one-shot
npm run build            # TypeScript check
npm run verify           # lint templates + zones + fonts
npm test                 # snapshot tests (seeds goldens on first run)
npm run dither-test      # writes ../docs/dither-test-results.md
npm run bake:clock-glyphs  # bake Fraunces digit/colon glyphs into firmware/src/generated/
```

`bake:clock-glyphs` is the build-time tool that produces the on-device
clock-zone composer's bitmap tables. Run after editing any `.clock`,
`.gv-clock`, `.np-clock`, or `.gt-corner-time` CSS selector — the
firmware build picks up the regenerated `clock_glyphs.{h,cpp}`.

## Endpoints

| Path | Purpose |
| ---- | ------- |
| `GET /healthz` | 200 + `{status, playwright_ready}` |
| `GET /display/{mode}.png` | Rendered PNG at 1200×825, single-channel 8-bit greyscale |
| `GET /display/{mode}/preview` | Human-facing HTML preview |
| `GET /display/{mode}/clock-zone.json` | `{x, y, w, h, font_size}` of the clock element on the most recent render of `{mode}`. 404 if the mode hasn't rendered yet or doesn't have a single clock element (Night splits hh/mm). Firmware reads this after every Full so partial-update digits land at the same pixels the Full painted. |
| `POST /inputs/:name` | Atomic write of an input JSON file (HA publisher target) |
| `GET /dither-test` | In-browser harness viewer |
| `GET /static/...` | CSS and self-hosted fonts |
| `GET /inputs/{file}` | Input JSON files (used by templates for image src, etc.) |

Modes: `summary`, `weather`, `gallery`, `night`, `now-playing`.

The PNG response also carries the clock zone in an `x-clock-zone` HTTP
header (`x=… y=… w=… h=… font_size=…`) so a client can read both in one
round-trip if it wants to.

## Inputs

By default the renderer reads JSON from `renderer/inputs/`. Override with
`RENDERER_INPUTS_DIR=/path/to/inputs`. Missing required inputs return 503,
with one exception: `device.json` is optional on every face — when absent
the battery indicator falls back to its graceful-degradation em-dash per
the `dashboard-faces` spec.

Per mode (current; see `src/modes/index.ts:gather*` for the canonical list):

- `summary` ← `clock, weather, news, pairing` (`sonos`, `device` optional)
- `weather` ← `clock, weather` (`device` optional)
- `gallery` ← `clock, pairing` (`device` optional)
- `night` ← `clock, weather, pairing` (`device` optional)
- `now-playing` ← `clock, sonos` (`device` optional)

See `src/modes/schema.ts` for the Zod contracts. `news` has been
simplified to a deterministic single-item smart-pill body sourced from
the daily summary item's YAML sidecar — the live-LLM regen pipeline
that used to overwrite it on every HA restart was removed.

### Now-Playing enrichment

When HA POSTs `sonos.json` with a Spotify `media_content_id`, the renderer
runs an enrichment pipeline (`src/enrichment/`) before persisting it:

- Spotify Web API (Client Credentials flow) for canonical track / album /
  artist data including the ISRC.
- MusicBrainz (politely, per their TOU) by ISRC for work-rel composer,
  work type, performer roles, and `first-release-date`.
- A classifier (`enrichment/classify.ts`) decides whether the track is
  classical and, when so, splits the title into `work` / `movement`.
- Spotify's stock edition suffixes (`" - 2021 Remaster"`, `"(Deluxe
  Edition)"`, etc.) are stripped from title and album so they don't leak
  onto the panel — for both classical and non-classical layouts.

Output fields are added in-place on the persisted `sonos.json`:
`classical`, `composer`, `work`, `movement`, `performers[]`,
`first_release_year`. The Now-Playing template renders a
composer-anchored layout when `classical: true` and a track-anchored
layout otherwise. Both share the same three-row anatomy
(label · primary · strip + year row).

Enrichment results are cached on disk under `cache/` indefinitely
(keyed by Spotify track id, ISRC, MB work MBID, MB artist MBID).
Recording metadata is immutable, so no TTL applies.

When Spotify or MB are unreachable, the renderer falls back to the
non-classical layout populated from `title` / `artist` / `album` alone.

Album art is fetched at render time through the same-origin
`/ha-proxy/api/media_player_proxy/...` route (Chromium inside Playwright
on the renderer host cannot reach the HA VM directly; the proxy shells
to curl). The proxy is **fast-fail**: short timeouts so a slow HA
doesn't stall the Full. If the fetch fails for any reason, the template
swaps to a baked fallback image at `templates/now-playing/fallback.jpg`
via an inline `onerror` handler — Now-Playing always renders.

Secrets (`spotify_client_id`, `spotify_client_secret`,
`musicbrainz_user_agent`) are read directly from `ha/secrets.yaml` at
startup by `src/enrichment/secrets.ts`. When any field is missing the
enrichment pipeline is disabled and the renderer falls back to the
non-classical layout.

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

The service restarts on crash (`KeepAlive`), throttled to 10 s. Logs go
to `/tmp/inkplate-renderer.{out,err}.log`.

The `serve()` startup goes through `listenWithRetry()` (`src/server.ts`),
which retries `EADDRINUSE` for up to 180 s with 1 s backoff. This covers
the macOS `TIME_WAIT` window after a launchd restart (typ. 30–60 s),
where the previous instance's socket hasn't been fully released yet.
Without the retry, launchd's blanket respawn-and-die loop would spam
the err log with hundreds of stack traces. Companion fix: graceful
shutdown waits for `server.close()` to finish before `process.exit()`,
so the kernel cleanly releases the socket instead of leaving it
half-closed. `uncaughtException` / `unhandledRejection` are caught and
logged so a stray Playwright timeout doesn't crash the process.

If `listenWithRetry` exhausts its 180 s budget the process exits 75
(`EX_TEMPFAIL`) and launchd respawns from scratch — that path is
genuinely a hard failure (something else is squatting the port).

## Snapshot tests

`npm test` renders every mode against `test/fixtures/*.json` and compares to
`test/__golden__/{mode}.png`. Diffs over 5 pixels fail. First run seeds the
goldens. Re-seed deliberately with `UPDATE_GOLDENS=1 npm test`.
