## Why

Today's HA override cascade treats priority as a single rule that governs both *what can activate* and *what's visible*. A tap during Now-Playing is suppressed — "music wins; stop the music if you want the dashboard back." In practice this is the wrong default: a tap is deliberate, effortful input; Sonos playing is an ambient state. The user who taps the frame during a podcast to glance at the rain forecast does not want to pause their podcast to do so.

The same latent rigidity produces two small bugs:

1. Re-triggering the same override (a second single-tap during an active peek; a double-tap during an active toggle) self-overwrites `prior_override` with the current state, losing the original pre-override value.
2. HA's time-trigger (`at: input_datetime`) does not back-fire for times already in the past. If HA restarts mid-peek and the expiry has elapsed during the restart, the peek override is stuck until a schedule boundary happens to clear it.

This change separates activation from deactivation: activation is explicit-beats-ambient (taps always activate outside quiet hours), deactivation consults a single shared restore cascade that selects the right prior state — including re-latching Now-Playing when music is still playing after a peek expires. It also shortens the peek window to 60 s (matching the device's 60 s timer cadence) and fixes the two bugs.

## What Changes

- **Single-tap during Now-Playing**: allowed. Activates `weather_peek` with `prior = now_playing`. On 60 s expiry, if Sonos is still playing, restores `now_playing`.
- **Double-tap during Now-Playing**: remains suppressed. Toggle's persistence (until next schedule boundary) interacts badly with multi-hour music sessions; deliberate asymmetry.
- **Peek window**: `input_number.inkplate_weather_peek_seconds` default 300 → 60.
- **Bug fix — `prior != active` invariant**: every activation guards the prior-save step with `active_override != <new state>`. Re-triggering the same state refreshes timers/faces but leaves `prior_override` untouched.
- **Unified restore cascade**: one selection rule, reused by the `weather_peek` expiry, the `now_playing` linger expiry, and (new) the HA-start stale-peek cleanup:
    1. `prior == now_playing` AND Sonos playing → restore `now_playing`
    2. `prior == weather_peek` AND expiry still future → restore `weather_peek`
    3. `prior == summary_gallery_toggle` → restore `summary_gallery_toggle`
    4. else → `schedule`
- **Linger-expired guard**: add `active_override == now_playing` condition to `inkplate_sonos_linger_expired`. Prevents the linger fire-event from overwriting a weather-peek that was activated by a tap during the linger window.
- **HA-start cleanup**: new automation `inkplate_ha_start_stale_peek_cleanup` runs the restore cascade if we boot with `active_override == weather_peek` and `peek_expires_at < now()`.
- **Quiet-hours policy unchanged**: gestures and Sonos activation remain suppressed during quiet hours. Rationale (accidental frame contact at 3 AM) is orthogonal to the now_playing rationale.

## Capabilities

### Modified Capabilities

- `ha-override-state` (this change ratifies the capability name; prior to this change the behaviour lived in automations without a named spec): the override lifecycle, activation rules, and deactivation cascade become normative.

## Impact

- **Files edited**:
  - `ha/automations/gesture_override.yaml` — drop `!= now_playing` guard on single-tap; add self-overwrite guards on both taps; replace peek-expiry restore block with the unified cascade; new HA-start cleanup automation.
  - `ha/automations/now_playing_override.yaml` — add `active_override == now_playing` condition on linger-expired; replace restore block with the unified cascade.
  - `ha/integrations/helpers.yaml` — `inkplate_weather_peek_seconds.initial: 300 → 60`; comment updates on `inkplate_active_override` and `inkplate_prior_override`.
  - `ha/docs/architecture.md` — replace single-priority-cascade state machine with the activation / deactivation split; document the unified restore cascade and the `prior != active` invariant.
- **No firmware change**. The firmware already publishes gestures and draws whatever retained `active_mode` HA sets.
- **No renderer change**.
- **No simulator change required**; the web `/sim` (`pairing/corpus_review.py`) already publishes the same MQTT gesture payload a real device does, so the new behaviour is exercised end-to-end the moment HA reloads the package.
- **Operator deploy**: standard `make deploy-ha` / `ha/deploy.sh`. No migration.
