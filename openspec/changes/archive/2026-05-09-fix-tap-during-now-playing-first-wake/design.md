# Design — fix-tap-during-now-playing-first-wake

## Background

Two facts converge:

1. The device cannot be remotely woken from deep sleep over WiFi. A wake pulse from HA is best-effort and only acts on a device that is already in its post-wake grace window. So when the operator starts music, the device typically does not flip to now-playing on its own — the screen stays on whatever the prior tier had drawn, sometimes for the full 30 min until the next timer-Full wake.

2. The operator's natural recovery for this is to **double-tap the device**. The IMU wake fires reliably; the firmware publishes the gesture, opens a 2 s grace window listening on `inkplate/command/gesture_response`, and either receives a face name from HA (and draws it) or times out and falls back to whatever's retained on `inkplate/command/active_mode`.

The fix described in this design assumes those two mechanisms remain unchanged. It only adjusts what HA publishes during the grace window when the override is `now_playing`.

## Why use the mirror sensor as the discriminator

Originally I considered three options for distinguishing first-wake taps from subsequent-peek taps:

- **A. `input_boolean` flag set on Sonos start, cleared on first wake.** Requires new state, fragile across HA restarts, dies if a Poll-driven wake draws now-playing without consuming the flag (the flag would still say "first wake pending" even though the device is already on now-playing).
- **B. Track "device active_mode" history and inspect the latest entry.** Effectively the same data the mirror already carries.
- **C. Read `sensor.inkplate_commanded_face` at trigger time.** The mirror, post-2026-05-08, reflects the face the device most recently drew (sourced from `inkplate/state/device.active_mode`).

Option C requires zero new state. It also degrades gracefully: cold boot or never-published device → mirror is `unavailable`; `unavailable != 'now-playing'` is true; first-wake handler runs, draws now-playing. That's the right cold-boot behaviour.

A subtle benefit: the mirror sees Poll-driven mode changes too. If the firmware's session-aware Poll cadence wakes the device mid-session and draws now-playing without any user tap, the mirror updates. The next user tap correctly takes the peek branch, not the first-wake branch. No bookkeeping needed.

## Why the peek target is `weather`, not `tier_main`

The original `peek_face = tier_main` (gallery in midday/evening, summary in morning) was modeled on the schedule-tap handler, where the user is navigating between scheduled faces. During music, the use case is different: the operator wants a quick ambient glance at conditions outside, not at today's curated gallery item. Operator confirmed in conversation 2026-05-09. One-line change.

`weather` always works as a peek target — Night-tier suppression is already handled by the existing `m >= 22*60 or m < 6*60+30` quiet-window condition.

## Why two automations rather than one with `choose`

Two reasons:

1. The `mode` directives differ. The first-wake handler is `mode: single` (one shot per tap; idempotent); the peek handler is `mode: restart` (a tap during a peek restarts the 60 s timer). HA automations have a single `mode` per top-level definition. Splitting is the cleanest way to give each branch its appropriate concurrency model.
2. Readability. Two named automations show up distinctly in the HA logbook, which makes operator-side debugging easier ("did the first-wake fire or did the peek fire?"). Merging into a single `choose` block hides the branch behind a generic automation entry.

The two automations do not race: their conditions are mutually exclusive (mirror == 'now-playing' XOR mirror != 'now-playing'). Both fire on every gesture but only one passes its conditions.

## Edge cases and how this design handles them

| Case | Mirror state at tap | Branch taken | Outcome |
|---|---|---|---|
| Music just started, device asleep, screen on stale weather | `weather` | first-wake | publish `gesture_response = now-playing` → device draws now-playing ✓ |
| Music playing, device on now-playing, operator taps to glance at weather | `now-playing` | peek | 60 s peek to weather, auto-revert ✓ |
| Operator taps a second time during the peek | `weather` | first-wake | back to now-playing immediately; the still-running peek's 60 s timer revert is a no-op (mode-already-now-playing) ✓ |
| Music starts during a schedule-tap-flip (mid-cycle, mirror = `gallery`) | `gallery` | first-wake | publish `gesture_response = now-playing` → device draws now-playing ✓ |
| Operator taps while screen is showing now-playing from a Poll-driven wake (no operator tap to start session) | `now-playing` | peek | 60 s weather peek ✓ (matches the "subsequent tap" intent) |
| Cold boot — device has never published state, mirror = `unavailable` | `unavailable` | first-wake | publishes now-playing; firmware reads retained active_mode = now-playing on grace-window timeout fallback either way ✓ |
| Quiet hours | (any) | neither (quiet-hours guard rejects both conditions) | no publish; firmware grace window times out; firmware reads retained active_mode ✓ |

## Out of scope

- The legacy precedence-stack table at `now-playing-override/spec.md:82-101` still references `single-tap Weather peek (5-min window)` and `double-tap Summary/Gallery toggle`, neither of which exists in the current automation set. They were excised from the code months ago but the spec wasn't updated. Cleaning that up is a separate change; this one only ADDs a new Requirement.
- Removing the device-side wake-pulse contract or otherwise making music-start a guaranteed wake. That requires a hardware change (low-power radio wake pin or a button) and is not what the operator wants — the double-tap workflow is intentional.
- Adjusting the Sonos-start automation, the linger logic, or any other part of the now-playing flow.

## Build version

No firmware change. No `kBuildVersion` bump. HA validates and reloads automations cleanly via `ha/deploy.sh`.
