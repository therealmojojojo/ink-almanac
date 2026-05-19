# now-playing-override Specification — delta

## ADDED Requirements

### Requirement: HA-start reconciliation

When Home Assistant starts, the now-playing activation rule SHALL be re-evaluated. State-change triggers do not fire for transitions HA was not observing — so any Sonos `→ playing` transition that occurred while HA was restarting (deploy, supervisor update, host reboot) is otherwise lost. Without reconciliation, the override remains on whatever value persisted across the restart, which can disagree with current Sonos state.

On `homeassistant.start`, if `media_player.kitchen_sonos == 'playing'` AND `input_text.inkplate_active_override != 'now_playing'` AND it is outside quiet hours, HA SHALL run the activation cascade: save the current `active_override` to `prior_override`, set `active_override = now_playing`, cancel any running linger timer, refresh `now_playing_content_id` from current Sonos media, publish `inkplate/command/active_mode = now-playing` retained, and publish a wake pulse to `inkplate/command/wake`.

If Sonos's integration is still reconnecting at `homeassistant.start` (state is `unavailable`), the condition guard fails and no action is taken; the subsequent `unavailable → playing` transition is handled by the existing `inkplate_sonos_play_start` activation path.

This Requirement does not introduce a new state transition. It closes a coverage gap in the existing activation rule by adding a third trigger source (alongside `media_player → playing` and quiet-hours-end re-eval) that funnels into the same cascade.

#### Scenario: HA restart while music is playing, override was lost mid-restart

- **WHEN** music is playing on `media_player.kitchen_sonos`, the operator runs `ha/deploy.sh` which restarts HA core, and during the restart window Sonos's integration briefly reports `unavailable` so the now-playing-stopped automation flips `active_override` to `schedule` before HA goes down; HA finishes restarting and `media_player.kitchen_sonos` is `playing` again
- **THEN** within seconds of `homeassistant.start`, the new HA-start reconcile automation fires, sees Sonos playing and override == `schedule`, runs the activation cascade, and the override returns to `now_playing` with retained `active_mode = now-playing` republished. The Inkplate's next wake (timer, Poll, or operator tap) draws the now-playing face.
