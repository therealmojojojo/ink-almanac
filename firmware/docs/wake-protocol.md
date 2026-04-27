# Wake protocol

How HA signals the device to change what it's showing, and how the
device reports its state back.

The full HA ⇄ Renderer ⇄ Device state machine lives in
`ha/docs/architecture.md` — this file is the device-side reference
(topics, reasons, and refresh rules).

## MQTT topics

| Topic | Direction | Retained | Payload |
| ----- | --------- | -------- | ------- |
| `inkplate/command/active_mode` | HA → device | yes | `summary` \| `weather` \| `gallery` \| `night` \| `now-playing` (or `{"mode":"..."}`) |
| `inkplate/command/wake` | HA → device | no | empty — triggers HA-command wake path |
| `inkplate/state/gesture` | device → HA | no | `{"kind":"single"\|"double"}` |
| `inkplate/state/device` | device → HA | yes | `{voltage, percentage, wake_reason, active_mode, build}` |

## HTTP endpoints (renderer)

In addition to the MQTT command surface, the device pulls two endpoints
from the renderer on each Full wake:

| Path | When | What |
| --- | --- | --- |
| `GET /display/:mode.png` | every Full | 1200 × 825 single-channel 8-bit greyscale PNG of the resolved face. |
| `GET /display/:mode/clock-zone.json` | after the PNG fetch on Full | `{x, y, w, h, font_size}` of the clock element on the most recent render. Cached in `Persisted` RTC slow memory so subsequent Partial wakes can pin their offline-composed clock digits at the same pixels the Full painted. 404 means the mode has no single clock element (Night splits hh/mm). |

The clock-zone JSON is a relatively new addition; see `firmware/README.md`
for the partial-refresh path that consumes it. The PNG response also
exposes the clock zone in an `x-clock-zone` HTTP header
(`x=… y=… w=… h=… font_size=…`) so an alternate firmware can read both
in one round-trip.

## Refresh schedule

Source of truth: `firmware/src/wake.cpp:tierFor()` (per-tier cadences) +
`ha/automations/schedule.yaml` (face alternation per tier). Anything in
this section that disagrees with those files is wrong.

### Cadence by tier

The day is partitioned into four tiers. Within a tier, the planner
classifies every minute into one of five paths (Skip / Partial / Poll /
PollPartial / Full) by simple modular arithmetic on `minute_of_day`.

| Tier | Hours | Full | Poll | Partial / PollPartial | Skip | Faces shown |
| --- | --- | --- | --- | --- | --- | --- |
| Morning | 06:30 – 10:00 | every 15 min (`:00,:15,:30,:45`) | every 3 min (`:03,:06,:09,:12,…`) | **Partial** every other minute (`:01,:02,:04,:05,:07,…`) | — | Summary ↔ Weather, alternates every 15 min |
| Midday | 10:00 – 17:00 | every 30 min (`:00,:30`) | (none standalone) | **PollPartial** every 5 min (`:05,:10,:15,:20,:25`) | all other minutes | Gallery ↔ Weather, alternates every 30 min |
| Evening | 17:00 – 22:00 | every 15 min | every 3 min | **Partial** every other minute | — | Gallery ↔ Weather, alternates every 15 min |
| Night | 22:00 – 06:30 | every 15 min | — | — | all other minutes | Night |

### What each path does

| Path | Wi-Fi up? | MQTT read? | HTTP render fetch? | Draw | Approx. cost |
| --- | --- | --- | --- | --- | --- |
| Skip | no | no | no | none — re-arm + deep-sleep | ~0 |
| Partial | no | no | no | clock zone only, 1-bit `partialUpdate` × 2 (seed + new) | ~0.06 mAh, ~250 ms |
| Poll | yes | yes (`active_mode`) | only if mode changed → Full | none unless mode changed | ~0.5 mAh per poll |
| PollPartial | yes | yes | only if mode changed → Full | clock zone if same mode (else Full) | ~0.5 mAh + ~0.06 mAh |
| Full | yes | yes | yes (PNG + clock-zone JSON) | whole-panel 3-bit refresh + 2 post-Full cleanup pulses on the clock zone | ~3 mAh, ~6–9 s |

### Per-face partial support

Whether `doPartial` actually composes a clock for the active face depends
on whether the face's clock font size has a baked Fraunces glyph preset
in `firmware/src/generated/clock_glyphs.{h,cpp}` (built by
`renderer/src/tools/bake-clock-glyphs.ts`).

| Face | Clock element | Font size | Baked preset | Partials render? |
| --- | --- | --- | --- | --- |
| Summary | `.summary-top .clock` | 160u | `kSummaryClock` | yes |
| Weather | `.weather-header .clock` | 44u | `kCompactClock` | yes |
| Gallery — visual landscape | `.gv-caption .clock` | 44u | `kCompactClock` | yes |
| Gallery — visual split | `.gv-root.gv-split .gv-clock` | 28u | `kCornerClock` | yes |
| Gallery — text | `.gt-corner-time` | 28u | `kCornerClock` | yes |
| NowPlaying | `.np-clock` | 28u | `kCornerClock` | n/a — planner forces Full every minute (`wake.cpp:pathForMinute`) |
| Night | (split `.hh` / `.mm`) | — | — | n/a — tier has no Partial cadence and renderer returns 404 |

### Overrides on top of the planner

| Trigger | Effect | Where |
| --- | --- | --- |
| Cold boot, OTA, `inkplate/command/wake` | Forces `Path::Full` regardless of cadence | `main_loop.cpp::tick` |
| Confirmed IMU tap | Reason becomes `IMU` → Full this wake; tap-ack pulse fires first | `main_loop.cpp::tick` |
| `current_mode == NowPlaying` | Planner returns Full every minute (cadence ignored) | `wake.cpp::pathForMinute` |
| Mode change detected at Poll / PollPartial | Promotes to Full of the new mode this wake | `main_loop.cpp` Poll / PollPartial branches |
| No cached clock zone or no matching baked preset | `doPartial` returns false → caller promotes to Full | `main_loop.cpp::doPartial` |
| Quiet-hours guard (HA-side) | Suppresses tap-driven mode changes; firmware's tier wakes still run | `ha/automations/gesture_override.yaml` |

### Worked example — one Midday hour, Gallery active

Midday tier with Gallery as the alternation phase. 12:00 to 13:00, in
minute order:

| Min | Path | What happens |
| --- | --- | --- |
| :00 | Full | Wi-Fi + MQTT + fetch Gallery PNG + 3-bit refresh + clock-zone fetch + 2 cleanup pulses |
| :01–:04 | Skip | re-arm + sleep |
| :05 | PollPartial | Wi-Fi + MQTT poll; same mode → 1-bit partial of clock zone (12:05) |
| :06–:09 | Skip | sleep |
| :10, :15, :20, :25 | PollPartial | partials at each cadence boundary |
| :30 | Full | next Full boundary |
| :31–:34 | Skip | sleep |
| :35, :40, :45, :50, :55 | PollPartial | partials |
| 13:00 | Full | next boundary |

So one Midday hour with Gallery active = **2 Fulls + 10 PollPartials + 48
Skips**. For comparison, an Evening hour with Gallery (or a Morning hour
with Summary) = **4 Fulls + 16 Polls + 40 Partials**.

## Resolving active mode

On every natural wake, the device reads retained `active_mode` from the
broker via a one-shot subscribe. If missing or unknown, it falls back to a
time-of-day heuristic:

| Hour (UTC, local if the clock is synchronized to local TZ) | Fallback mode |
| --- | --- |
| 06–10 | Summary |
| 10–22 | Weather |
| 22–06 | Night |

Active-mode overrides (Gallery pinned, Now-Playing fast-path) are HA's
responsibility; the device simply obeys the retained topic.

## Wake reasons

Published in `inkplate/state/device.wake_reason`:

- `cold_boot` — first boot or power cycle.
- `post_ota` — first boot after an OTA update.
- `timer` — scheduled mode-timer wake.
- `imu` — tap / double-tap from the LSM6DSO INT1 pin. Note: INT1 is
  wired to the same GPIO 36 net as the SW3 wake button (see
  `gestures.md` "Wiring"); on every `ext0` wake the firmware reads
  `WAKE_UP_SRC` to confirm a real tap event before classifying as `imu`,
  otherwise it re-sleeps without refreshing.
- `ha_command` — HA published to `inkplate/command/wake` (includes
  motion-triggered wakes from the HA-side IKEA sensor; the device does not
  distinguish motion from other HA-initiated wakes).
- `sonos_fast_path` — Sonos-window short timer; early-returns if mode unchanged.

(Note: `pir` was removed when motion detection moved off-device; see
`openspec/changes/move-pir-to-ha-motion/`.)

## Fast-path semantics

`Reason::SonosFastPath` with an unchanged active mode: the device re-arms
and sleeps without fetching or refreshing. This bounds the Now-Playing
activation latency to `kSonosFastPathSec` (currently 60 s — the daytime
mode timers are also 60 s, so the fast path is largely redundant under
the current schedule, retained for non-planner code paths).

## Ghost cadence

Legacy: every `kGhostClearPartialCount` partial refreshes within a mode,
the next refresh would be promoted to a full refresh. Currently dormant
— the post-Full zone cleanup (two 1-bit pulses immediately after every
Full's 3-bit draw) plus the seed-then-draw partial path together keep
ghosts cleared without the global counter. The constant remains in
`config.h` so the mechanism can be re-enabled if a future configuration
reintroduces ghosting.
