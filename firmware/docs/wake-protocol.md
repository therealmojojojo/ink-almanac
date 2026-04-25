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
activation latency to `kSonosFastPathSec` (default 180 s) without forcing
a full 3-minute-cadence network round-trip.

## Ghost cadence

Every `kGhostClearPartialCount` partial refreshes within a mode, the next
refresh is promoted to a full refresh to clear accumulated ghosting. The
counter resets on every full refresh.
