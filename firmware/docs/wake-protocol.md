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
