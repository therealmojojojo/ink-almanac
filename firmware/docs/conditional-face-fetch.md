# Conditional face fetch (future optimization)

> Status: not implemented. Captured here so the analysis isn't lost.

## Problem

Every Full wake re-fetches the active face PNG from the renderer, even
when the underlying inputs haven't changed since the previous Full. At
the 15-minute Full cadence in Morning / Evening tiers and the 30-minute
cadence in Midday, that's ~56 face fetches per day in steady state —
4–9 MB of PNG traffic, almost all redundant for the typical case where
the only change between two Fulls is the embedded clock-zone digits.

On a healthy Wi-Fi link the cost is invisible. On a marginal link
(-75 dBm and below), TCP retransmits multiply the link-layer cost 2-3×,
and most of the wake's elapsed time is spent on a fetch that returns
content the device already had.

## What changes between consecutive Fulls

Most Fulls are pixel-equivalent to their predecessor:

- Clock zone (the embedded digits): always different, but the firmware's
  partial-refresh path already over-paints the clock zone every minute
  using locally-rasterised glyphs. The renderer's pre-baked digits in
  the Full PNG are just the "starting" minute; partials replace them
  immediately.
- Weather body: ~99% identical between two consecutive Fulls 15 min
  apart, unless the operator's MET.no template sensor crossed an
  hourly boundary between them.
- Astro / smart-pill / now-playing: change at 06:00 / 07:00 / track
  changes — not on the Full cadence.

In other words: most of the bytes the device fetches are bytes it
already has on the panel.

## Standard solution

HTTP/1.1 conditional fetch:

1. Renderer adds a `Last-Modified` response header to `/display/<mode>.png`
   based on `max(stat(input).mtime for input in face_inputs)`. The
   complete list of inputs is in `renderer/src/modes/<mode>.ts`.
2. Firmware persists the previous successful fetch's `Last-Modified` value
   per mode in RTC slow memory (~4 modes × 8 chars = 32 B alongside
   `g_persisted`).
3. Firmware sends `If-Modified-Since: <prev-last-modified>` on the next
   fetch.
4. Renderer returns `304 Not Modified` (no body) if no input has changed.
5. Firmware on `304` skips `panel.drawImage()`, leaves the panel content
   alone, and only repaints the clock zone via the existing partial
   path.

## Expected savings

At 15-min Full cadence with hourly weather updates and daily astro
updates: ~95% of Fulls become 304s. Bandwidth drops from ~5 MB/day to
~250 KB/day. Wake duration on marginal Wi-Fi drops from 6-9 s to 2-3 s
(no PNG body to receive). Battery cost roughly halves on the active-wake
budget (which today is the dominant term per `power-budget.md`).

## Implementation sketch

### Renderer side (~30 lines)

In `renderer/src/server.ts` for the `/display/:mode.png` route:

```ts
const inputsForMode = (mode: Mode) => {
  // Per-mode list of files this face depends on. Keep this aligned with
  // the templates and modes/<mode>.ts logic.
  switch (mode) {
    case 'weather': return ['inputs/weather.json', 'inputs/clock.json'];
    case 'summary': return ['inputs/pairing.json', 'inputs/news.json',
                            'inputs/clock.json', 'inputs/companion.jpg'];
    // …
  }
};

const lastModified = Math.max(
  ...inputsForMode(mode).map(p => statSync(p).mtimeMs)
);
const lastModifiedHttp = new Date(lastModified).toUTCString();

const ims = req.headers['if-modified-since'];
if (ims && Date.parse(ims) >= lastModified) {
  return res.status(304).set('Last-Modified', lastModifiedHttp).send();
}
res.set('Last-Modified', lastModifiedHttp);
// existing PNG render path
```

Caveat: `inputs/clock.json` updates every minute. If we naively include
it in the inputs-list, every Full > 1 min after the previous one looks
"changed." Two options:

- **Exclude clock.json from the inputs-list.** The Full's clock-zone
  pixels become slightly stale at the second of capture, but the
  firmware's partial-refresh already over-paints those pixels on every
  minute boundary. So the panel still shows the right time. This is the
  cleaner approach.
- **Round mtime to the nearest hour.** Cruder; not recommended.

Use option (a) — exclude clock.json. The renderer's response will only
change when *real* content changed.

### Firmware side (~40 lines)

Persist a small per-mode `last_modified` cache in RTC slow memory:

```cpp
struct PerModeFetchCache {
  uint8_t valid;
  char last_modified[32];  // HTTP-date format, NUL-terminated
};
RTC_DATA_ATTR PerModeFetchCache g_fetch_cache[5];  // one per Mode
```

In `RealTransport::httpGet`, accept and surface response headers; pass
`If-Modified-Since: <cached>` on each fetch; return the new
`Last-Modified` to the caller.

In `doFull`:
```cpp
auto cached_lm = g_fetch_cache[active].valid
                   ? g_fetch_cache[active].last_modified : nullptr;
auto resp = h.transport.httpGetConditional(url, cached_lm);
if (resp.status == 304) {
  FW_LOG("face unchanged (304); skipping draw");
  // Keep g_fetch_cache as-is.
  draw_succeeded = true;  // panel already shows the right content
} else if (resp.status == 200) {
  h.display.drawImage(...);  // existing path
  std::strncpy(g_fetch_cache[active].last_modified,
               resp.last_modified.c_str(), 31);
  g_fetch_cache[active].valid = 1;
  draw_succeeded = true;
}
```

The post-Full clock-zone seed runs unconditionally on `draw_succeeded`,
so the partial-refresh path keeps working correctly even on 304 paths.

## Why this isn't done yet

1. **Adds a per-mode RTC field**, growing the persisted struct (currently
   12 bytes). Not large, but increases the surface for the documented
   ESP32 RTC `volatile` footgun.
2. **Renderer needs a per-mode inputs-list** that stays accurate as
   templates evolve. Drift between the list and the actual template
   read paths produces silent cache-staleness bugs (panel shows old
   data because we said "not modified" when the template actually
   reads a file we forgot to list).
3. **The "obvious" approach (excluding clock.json) means the renderer's
   embedded clock in the Full PNG is up to 1 hour stale.** Functionally
   fine because partials over-paint, but a viewer who catches the panel
   between minute-tick partials might see the wrong digits briefly. The
   visual bug is cosmetic and bounded to a single minute.
4. **It's not load-bearing.** A healthy Wi-Fi link makes the
   optimization invisible. The motivation is "make marginal links
   tolerable," which is a battery and reliability win, not a
   functionality requirement.

## Related future work

- **Conditional fetch becomes much more valuable if combined with mid-tier
  power-save profiles** (longer Full cadence at low battery — `% changed
  often dominates if Fulls are rare).
- **Firmware-side raw-PNG cache in flash**: the device could keep the
  last successful PNG and replay it after a brief panel-clear. Adds
  flash wear and complexity for marginal benefit; almost certainly
  not worth it on top of conditional fetch.

## Estimated effort if revisited

- Renderer changes: half a day, including a per-mode inputs-list test.
- Firmware changes: a day, mostly RTC-layout discipline +
  `httpGetConditional` plumbing through the HAL interface.
- Spec + tests: half a day.
- Coordinated rollout (renderer must ship before firmware to avoid 304s
  to a firmware that doesn't understand them): trivial in our deploy
  flow.

Total: ~2 days of focused work for a 95%-bandwidth-reduction win on
Fulls. Worth doing if Wi-Fi-marginal operation becomes a steady-state
concern.
