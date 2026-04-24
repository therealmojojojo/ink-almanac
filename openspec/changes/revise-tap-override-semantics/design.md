## Context

The override state machine lives in `ha/automations/*.yaml` and is the connective tissue between ambient signals (schedule boundaries, Sonos state), explicit signals (taps), and what retained MQTT topic the device trusts (`inkplate/command/active_mode`). The original design encoded priority as a *single* rule — one cascade decided both activation and visibility. That made the semantics easy to state ("highest wins") but produced a counter-intuitive outcome: a deliberate tap during music does nothing.

The user's mental model separates these. A tap is effortful and rare; it reflects intent. Music is background. Weather-peek is already the right escape-hatch shape: time-boxed, auto-reverts, non-destructive. It should just activate.

## Goals / Non-Goals

**Goals**:
- Tap during music works and auto-returns to music when the peek expires.
- Peek window matches the device's timer cadence so visible-weather time is predictable (60–120 s).
- `prior_override` is never lost to self-overwrite.
- A single restore cascade, reused everywhere deactivation happens.
- Stuck-peek across HA restart self-heals at boot.

**Non-Goals**:
- Repurposing double-tap as "next track" or any other Sonos command. Deliberate deferral — revisit as its own change if wanted.
- Relaxing quiet-hours suppression. Different rationale (accidental contact at night), different trade-off.
- Firmware changes. The device's publish-gesture-then-trust-retained-active_mode pattern is correct; no edit needed.
- Simulator changes in `firmware/test/`. The scenario harness already expresses "HA replies with <mode> on gesture" via `MockTransport::setPublishHook`; new scenarios can be added later if desired but are out of scope here.
- Restoring `weather_peek` as a destination from `now_playing` linger expiry in isolation of the `prior` check. The cascade only restores a state when the helper explicitly points at it.

## Decisions

### Activation is explicit-beats-ambient, except quiet hours

A tap is deliberate input; the device's form factor (IMU tap detection on a fridge-mounted panel) makes accidental gestures rare outside one narrow window — night, reaching for water, bumping the frame. That is exactly what quiet hours are for. Outside quiet hours, a tap is a signal of intent and should always activate.

Alternative considered: retain the priority cascade and add a "force" flag that taps use to preempt. Rejected because it keeps the single-cascade mental model that's already hard to reason about, just with a back door.

### Double-tap during `now_playing` stays suppressed

Double-tap's target state, `summary_gallery_toggle`, persists until the next schedule boundary (06:30 / 10:00 / 22:00). A single accidental double-tap during lunchtime music would leave the device on a toggled face for hours after the music stops. Making double-tap symmetric with single-tap would either (a) require shortening the toggle window (changing a semantic that works today) or (b) accept the multi-hour consequence of an accidental double-tap. Simpler to keep the guard.

The asymmetry is documented in `gesture_override.yaml` header and in `architecture.md`. If we later want double-tap to do something during music (e.g., next track), it lives as a separate change.

### Peek window = 60 s, matching `kSummaryTimerSec`

The device's timer cadence is 60 s. After peek expiry publishes retained `active_mode=<scheduled>`, the device sees the change on its next timer wake (≤60 s later). Visible-weather time lands in [60, 120] s, which is the natural granularity.

Alternative considered: keep 300 s. Rejected because the user's intent for a tap is "glance at the weather", not "read the weather for five minutes". 60 s is closer to the implied duration, and the user can always re-tap to extend (the re-trigger invariant now preserves `prior`).

### One restore cascade, three call sites

Today three expiry automations have three slightly different restore blocks (weather-peek expiry, linger expiry, and — now added — HA-start stale-peek cleanup). Duplication hides drift. The cascade is identical at each site and is now copy-pasted with identical Jinja variables. A future refactor could extract it into a shared script/template — deferred because HA YAML's macro support is thin and the copy is small (15 lines).

Importantly, the cascade's top branch — "if `prior == now_playing` and Sonos is playing, restore `now_playing`" — is new. This is what makes tap-during-music round-trip correctly.

### `prior != active` as a named invariant

The self-overwrite bug existed for both single-tap (tap-during-peek) and double-tap (re-toggle). Rather than patching each site separately, the fix is a guard condition on every `set prior = current` step: run it only when `current != <new state>`. Invariant named in the helper comment and in `architecture.md`.

### HA-start cleanup over a periodic watchdog

A periodic check ("every minute, if peek is stuck, revert") would cover more failure modes but adds a ticking automation for a rare failure. HA start is the only realistic way the expiry can be missed (the `at:` trigger handles every other case). One automation, `homeassistant: event: start`, no periodic cost.

## Risks / Trade-offs

- **Restore cascade complexity at the Jinja level**. Two `set`-style variables (`restore` and `restore_mode`) encode the same decision tree twice — once for the override value, once for the MQTT `active_mode` payload. Duplication is deliberate (HA's action variables can't share derived expressions cleanly) but is a maintenance tripwire: a change to the cascade must be made in two places per automation, and three times across two automations. Mitigation: the tree is shallow (4 branches), the files are reviewed together, and the derived mode payload is straightforward (`now_playing → now-playing`, `weather_peek → weather`, anything-else → `scheduled_face`).
- **60 s peek might feel too short for some users**. The `input_number` is still operator-editable 60..900. Default is the only thing that changed.
- **Tap-during-linger is now a real state transition** (previously suppressed by the `!= now_playing` guard). The added `active_override == now_playing` condition on `inkplate_sonos_linger_expired` is load-bearing: without it, the linger fire-event would overwrite the user's active peek. Reviewed against test scenarios; correct as long as that guard stands.
- **Self-overwrite guard changes the side-effect surface of gesture automations**. An automated test that counted `input_text.set_value` service calls would see one fewer call on re-triggered states. No known consumer; flagging for future work.

## Migration Plan

This change applies cleanly with no migration step. Operator deploys via `make deploy-ha`. At reload:

1. `inkplate_weather_peek_seconds` retains its current operator-edited value; only the default is changed (takes effect on a fresh install or helper reset).
2. The new automation `inkplate_ha_start_stale_peek_cleanup` is idempotent — if we load it with a non-stale peek, its conditions fail and it does nothing.
3. Existing in-flight overrides (an active peek at reload time) continue to expire via their existing `at:` trigger, unchanged.

Rollback: `git revert` the automation + helper + doc changes. No state changes required on the device or renderer.

## Open Questions

1. **Should we add a scenario test under `firmware/test/scenarios/` that exercises tap-during-music via `MockTransport::setPublishHook`?** Probably yes, but not in this change — keep the proposal focused on HA behaviour. File under "scenario-spec parity" in `add-device-simulation`.
2. **Should the restore cascade be extracted into a reusable HA script?** HA's script system supports parameters but not easy return values; the cleanest factoring is a template sensor or a Python helper. Neither is a clear win over the current copy. Defer unless a third deactivation site appears.
3. **Does the `inkplate_ha_start_stale_peek_cleanup` automation need a small start-delay to let state helpers settle after reload?** HA guarantees helpers are restored before the `homeassistant.started` event, so the immediate-fire pattern is safe. Flagging in case we see flaky behaviour in practice.
