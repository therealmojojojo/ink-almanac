# Design — local-clock-tick

## The essential trade

Every minute of stale clock is a UX failure. Every network round-trip per minute is a power failure. The design collapses the two by separating:

- **What happens every minute (or every 15 minutes at night):** a local draw. Cheap, quiet, no network.
- **What happens every 15–60 minutes:** a full fetch-and-refresh. Expensive, network-bound, but infrequent.

The device has everything it needs for the first case: an RTC, a bitmap font in flash, and a known clock-zone rectangle. The second case is unchanged from the prior design.

## Why PCF85063A, not ESP32 internal RTC

The ESP32's RTC lives in its RTC power domain — it survives deep sleep on the main LiPo, but it dies when the LiPo disconnects (battery swap, deep discharge, hard reset). The PCF85063A on Inkplate 10 is a dedicated external RTC chip with a CR2032 coin-cell backup; it keeps ticking through anything short of the coin cell dying (5–8 years).

For the local-tick architecture this matters: the device shows the wrong time until NTP syncs. NTP needs WiFi. WiFi needs ~5–10 s post-boot. Without the coin cell, every cold boot has a window of wrong-clock, which is exactly the UX we're trying to avoid.

With the coin cell + external RTC: the clock is correct from the first local-tick wake, regardless of network state. NTP sync is a refinement, not a prerequisite.

## Why local-draw over server-cropped sub-PNG

Considered but rejected: having the renderer expose `GET /display/{mode}/zone/clock.png` returning a tiny PNG of just the clock region. The device fetches this each minute-tick and partial-refreshes.

Rejected because: the WiFi round-trip is the dominant cost, not the image size. A 5 KB PNG still requires WiFi-associate (~5 s), HTTP (~1–2 s), and the current spike is ~90 mA for that whole window. Per-wake cost is ~0.4 mAh — 16× the local-draw cost. At 930 wakes/day this blows the battery budget.

Local draw costs ~0.025 mAh per wake because the wake cycle is a handful of I²C reads, a memcpy into the framebuffer, and a partial refresh. No radio comes up.

The trade is firmware-side font synchronization — solved by generating the GFXfont struct from the renderer's TTF at build time so both sides ship the same glyph shapes.

## Font synchronization contract

The renderer owns typography (via `add-rendering-pipeline` / `add-dashboard-faces`). The firmware should never have an independent opinion on what the clock font looks like. To enforce this:

- A build step (`renderer/scripts/gen-firmware-fonts.py` or similar) reads the renderer's TTF files and emits a `GFXfont` C header into `firmware/include/assets/fonts/`.
- The codegen emits a subset: digits `0–9`, colon `:`, and the lowercase alphabet + space + apostrophe for Night approximate-time phrases.
- Firmware's build depends on the header. If the renderer's font changes, the firmware header regenerates; the firmware either rebuilds or fails compilation because the glyph table version changed.
- Both renderer and firmware record a glyph-table version hash; firmware refuses to run local-tick draws if its glyph table version doesn't match the last-known zones.json version from the renderer.

This keeps typography coherent without coupling code paths.

## Night phrase algorithm

Shared between renderer and firmware. Pseudo-code:

```
fn nightPhrase(h: 0..23, m: 0..59) -> String:
  let hour12 = ((h + 11) % 12) + 1            // 1..12
  let nextHour12 = (hour12 % 12) + 1
  match m:
    0..=14  => format!("{H} o'clock",       H = word(hour12))
    15..=29 => format!("quarter past {H}",  H = word(hour12))
    30..=44 => format!("half past {H}",     H = word(hour12))
    45..=59 => format!("quarter to {H}",    H = word(nextHour12))

fn word(h12: 1..12) -> String:
  // "one", "two", "three", ..., "twelve"
```

The device ticks at `:00`, `:15`, `:30`, `:45` (aligned to the quarter); the renderer computes on each full fetch using the same function. Both land on the same string for any given `(h, m)`.

## Clock-zone coordinate sourcing

The renderer declares each face's clock-zone rectangle in `renderer/src/zones.ts`. A new endpoint serves it:

```
GET /display/zones.json

{
  "version": "sha256:…",            // hash of the zones source
  "faces": {
    "summary":     { "clock": { "x": ..., "y": ..., "w": ..., "h": ... } },
    "weather":     { "clock": { "x": ..., "y": ..., "w": ..., "h": ... } },
    "gallery":     { "clock": { "x": ..., "y": ..., "w": ..., "h": ... } },
    "night":       { "clock": { "x": ..., "y": ..., "w": ..., "h": ... } },
    "now-playing": { "clock": null }   // no local clock on this face
  }
}
```

Firmware flow:

1. **Cold boot / OTA boot:** fetch `zones.json`, compare `version` against the snapshot in RTC SRAM. If changed, persist the new snapshot to flash (LittleFS or equivalent) and update the RTC SRAM marker.
2. **Every wake thereafter:** use the RTC SRAM marker to look up the coords in flash; no fetch needed.
3. **If `zones.json` fetch fails at cold boot:** use the last-known-good snapshot from flash. Suppress local-tick if no snapshot exists yet (face will still render on full cycles).

## Status glyphs

Top-right, **overlapping the existing battery-indicator area**. One glyph visible at a time (or none); when no glyph is active, the battery indicator is visible as usual.

| Glyph | Size | Tone | Trigger | Cleared by |
|---|---|---|---|---|
| `ack` (thumbs-up) | ~32×32u | `--mid` (#555) | IMU wake identified | Next full refresh of the face |
| `error` (⚠) | ~32×32u | `--ink` (#000) | Fetch/MQTT failure | Next successful fetch |

Both are monochrome bitmaps pre-rendered to ship with firmware (`assets/glyphs/ack.bin`, `assets/glyphs/error.bin`). They occupy the same rectangle — emission is mutually exclusive. If both conditions are true (rare: tap during an outage), `error` wins.

**Battery-indicator interaction:** the renderer paints the battery percentage in the top-right on every full render (existing shared convention). When a status glyph is active, the firmware partial-refreshes the glyph bitmap *over* the battery indicator, hiding it temporarily. On the next full refresh — triggered by mode change, schedule boundary, ghost-clear, or successful retry after error — the whole face is repainted, which implicitly restores the battery indicator in that same spot. Users who want live battery telemetry consult HA (which receives it over MQTT); the on-face indicator is a "when you happen to glance" affordance, and the brief hiding during an `ack` flash or an `error` state is acceptable.

The status-slot rectangle is declared in `zones.json` as `faces.<mode>.status_slot` so firmware and renderer agree on its coordinates without needing a separate codegen pin. The renderer already paints into this rectangle (the battery indicator); this change just documents it as a named zone so firmware can target its partial-refresh precisely.

This supersedes the previous "tiny circle in the battery area, 6u square" corner indicator for renderer unreachability. Same location, same role, larger and more expressive glyphs.

## Sleep strategy — the revised table

| Period | Hours | Mode | Local-tick cadence | Full-fetch cadence | Sonos fast-path | IMU INT armed |
|---|---|---|---|---|---|---|
| Morning | 06:30–10:00 | Summary | 1 min | 15 min | 3 min (from 07:00) | yes |
| Daytime | 10:00–20:00 | Gallery | 1 min | 15 min | 3 min | yes |
| Evening | 20:00–22:00 | Gallery | 1 min | 30 min | — | yes |
| Night | 22:00–06:30 | Night | 15 min (quarters) | 60 min | — | yes |
| Now-Playing | variable | Now-Playing | — (no local tick) | 15 min | — | yes |

Rationale:

- Day full-fetch cadence is 15 min even in Gallery because data *other than* clock (battery, weather) matters and the visual hero can change on the pairing-day boundary.
- Evening relaxes full-fetch to 30 min because the content is mostly static and the user is often not in the kitchen.
- Night has no continuous tick — 15-min quarters are enough for the approximate-time phrasing.
- Now-Playing intentionally has no local tick; track changes come via HA wake-reason, and a clock on a Now-Playing face is secondary to the album art.

## Power budget sanity check

Using the power-model placeholder values (revisit after hardware measurement):

| Wake kind | mAh each | Count/day | Subtotal |
|---|---|---|---|
| Day local-tick | 0.025 | 930 | 23.3 |
| Night local-tick (quarter) | 0.025 | 34 | 0.85 |
| Day full-fetch | 1.08 | 62 (Morning 14 + Day 40 + Evening 8) | 67.0 |
| Night full-fetch | 1.08 | 8 | 8.6 |
| Sonos fast-path (early-return, Sonos window) | 0.04 | up to 260 | up to 10.4 |
| IMU-wakes + ack glyph | ~0.05 | ~10 | 0.5 |
| HA-initiated wake observations | — | — | folded into fast-path / timer |
| Quiescent | 4 | — | 4 |
| **Total** | | | **~115 mAh/day** |

42 × 115 = 4830 mAh — close to the 5000 mAh pack and just over the 4000 mAh usable budget. Tuning levers if we need to reduce:

- Drop Evening full-fetch to 60 min (–4 mAh/day).
- Drop Night local-tick entirely (–0.85 mAh/day; minor).
- Raise Day full-fetch to 20 min (–22 mAh/day; biggest lever).
- Skip local-tick in Gallery periods when clock zone isn't visible enough to matter (–6 mAh/day).

Revisit once hardware current draw is measured; the placeholder currents in `power-model.md` are known overestimates.

## Tap is a wake signal, not a semantic decision

The prior `device-firmware` "Tap detection" requirement read as if the firmware itself decided what a tap means ("treat a single tap as a request to activate Weather peek"). That conflates two things:

- **The raw event**: a tap happened, it was single or double.
- **The policy decision**: given the current override state, Sonos state, quiet-hours state, scheduled face, etc., what should the active face become?

The raw event is firmware's to detect. The policy decision is HA's — it already owns the override-precedence cascade (`ha/docs/architecture.md:112–123`) and the full face-selection state machine. Firmware that makes its own gesture-to-mode decisions would be a second, competing source of truth.

The spec update makes this explicit: firmware publishes the gesture, HA decides, firmware reads back the decision. To keep the UX snappy, the firmware does a short post-publish wait (default 2 s) on the `active_mode` topic so the tap-triggered face change can be drawn within the same wake cycle — avoiding the worst case where HA's decision isn't visible until the next full-cycle wake (up to 15 min later).

The 2 s grace window is a compromise:

- Long enough for a healthy HA to process the gesture, recompute the cascade, and republish retained `active_mode`.
- Short enough that it doesn't noticeably extend the wake time (the full-cycle wake is ~12 s anyway; the grace window fits inside the post-publish window the device is already open for).
- If it expires: the user sees the ack glyph, no face change, and the updated face lands on the next full-cycle wake. Honest, recoverable UX; no lost gestures.

This reframing also means the ack glyph reads correctly: it says "tap received," not "switching now." Sometimes the gesture is effectively suppressed (quiet hours + single tap), and the ack glyph without a follow-on face change is the right visual because it's true.

## Interaction with other in-flight changes

- **`add-device-firmware`** — the `Reason::LocalTick` path and the new cadence supersede the minute-tick rule in that change's "Thin-client main loop". This change's MODIFIED requirements replace those sections when both are archived; order of archive does not matter because the deltas are text-level replacements.
- **`move-pir-to-ha-motion`** — compatible. That change already modifies "Wake sources" to remove PIR; this change further modifies "Wake sources" to add `LocalTick` distinct from `Timer`. Both sets of edits stack.
- **`add-device-simulation`** — needs new mock paths for `Reason::LocalTick` and for the status-glyph partial-refresh calls. Scenarios added in this change's tasks list.
- **`add-rendering-pipeline`** — `GET /display/zones.json` is additive; no endpoints removed.
- **`add-dashboard-faces`** — Night face layout is MODIFIED (approximate phrasing replaces stacked precise clock); other face layouts are MODIFIED only to carry explicit `clock_zone` coordinates. Character-budget table gains a `night_phrase` entry replacing the former `hard_weather` + stacked-clock lines for Night.

## Explicitly out of scope

- **Dropping quiet-hours tap suppression.** Discussed in the conversation as a UX win; deferred to a follow-up change because it touches HA automations (not just device firmware) and isn't on the critical path for local-tick.
- **Now-Playing-during-Night policy refinement.** The current spec says music during quiet hours is suppressed; unchanged here.
- **Gesture fast-path** (where device fetches `/display/weather.png` directly on single-tap without waiting for HA to reconcile override state). Interesting but separate — goes in its own change so we can discuss the tradeoff between "instant peek" and "HA is always source of truth."
- **Night-face-with-no-clock** as an aesthetic option. You asked for approximate phrasing; if later you want the Night face to omit time entirely, that's a one-line spec edit.
- **Emoji glyphs proper** (colored, full Unicode). Out of scope for e-ink; we ship monochrome bitmaps that read as familiar symbols but are explicitly pre-rendered, not Unicode.
