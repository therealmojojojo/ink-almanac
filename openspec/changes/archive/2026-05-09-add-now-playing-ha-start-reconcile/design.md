# Design — add-now-playing-ha-start-reconcile

## Why a new automation rather than adding `homeassistant.start` to `inkplate_sonos_play_start`

The natural-looking fix is to add `- platform: homeassistant; event: start` to the existing `inkplate_sonos_play_start` triggers. That breaks two things:

1. **prior_override is clobbered.** `play_start`'s first action saves `prior_override = current active_override`. On HA-start where override survived as `now_playing` (the normal case — restart didn't lose Sonos state), this would overwrite the real prior with `now_playing`, breaking the linger-restore cascade later. We'd have to add a condition `active_override != now_playing` and tolerate that condition silently rejecting many normal play-transitions where override happened to already be now_playing (e.g. resume-during-linger). The semantics get muddled.

2. **No-op churn.** Every HA-start would fire the automation regardless of state, doing the full activation cascade even when override is already correct. That's harmless but noisy.

The existing `inkplate_sonos_quiet_hours_end_reeval` automation already establishes the "reconcile if needed" pattern: separate automation, gated on `Sonos playing AND override != now_playing`. The new HA-start automation follows the same shape exactly. Three reconcile sources (state-transition, quiet-hours-end, HA-start), three sibling automations, identical action bodies. The duplication is real but matches the existing pattern; consolidating into a single shared script is a separate refactor.

## Why act on `homeassistant.start` rather than a delayed trigger

`homeassistant.start` fires once HA core is up and integrations have loaded. By that point `media_player.kitchen_sonos` reflects the current Sonos state. If the integration is slow to reconnect (Sonos is briefly `unavailable` during the post-restart reconnect), the condition fails and the automation no-ops — the actual `→ playing` transition that follows the reconnect will fire `inkplate_sonos_play_start` normally and activate.

In other words, the new automation handles the case where Sonos was already `playing` at HA-start; the normal play-transition handles the case where it isn't yet. Together they cover both.

A short delay (e.g. 5 s) after `homeassistant.start` could improve robustness against extremely slow Sonos reconnects, but adds latency to a path the operator might be staring at. Skipped for now; revisit if the no-coverage gap turns out to be wide.

## Edge cases

| Scenario | Outcome |
|---|---|
| HA restart, Sonos was playing, override was `now_playing` (normal path) | Condition `override != now_playing` fails → no-op. ✓ |
| HA restart, Sonos was playing, override flipped to `schedule` mid-restart (today's incident) | All conditions pass → activate now_playing → publish active_mode + wake → mirror reconciles on next device wake. ✓ |
| HA restart, Sonos was idle / paused / off | Condition `media_player == playing` fails → no-op. ✓ |
| HA restart in quiet hours, Sonos playing | Quiet-hours guard fails → no-op (matches `play_start`'s behaviour). ✓ |
| HA restart, Sonos integration slow to reconnect; state is `unavailable` at `homeassistant.start` | `media_player == playing` is false → no-op. When integration reconnects and state goes to `playing`, `play_start` fires normally. ✓ |

## Out of scope

- Refactoring the three duplicated activation cascades (`play_start`, `quiet_hours_end_reeval`, `ha_start_reeval`) into a shared script. Worth doing later; not this change.
- Fixing the pre-existing double-activation behaviour where `play_start` fires alongside `play_resumed_during_linger` on a brief paused→playing transition (overwrites `prior_override` with `now_playing`). Separate bug, separate change.
- Making `ha/deploy.sh` Sonos-aware (post-restart reconciliation script). With this automation in place, the deploy doesn't need to know — HA handles it on its own. Drop the deploy-script idea.
