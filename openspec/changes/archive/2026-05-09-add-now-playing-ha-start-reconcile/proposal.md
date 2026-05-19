# Add HA-start reconciliation for now-playing override

> **Status — 2026-05-09**: drafted in response to a live failure during the deploy of `fix-tap-during-now-playing-first-wake`. Sonos cycled `unavailable → playing` while HA was mid-restart; the playing transition was missed; override stayed on `schedule` while music was playing; tap behaviour fired the schedule handler instead of the now-playing handler. Operator fix was a manual `automation.trigger` of the Sonos-started automation. This change closes the hole.

## Why

`inkplate_sonos_play_start` activates the now-playing override on `media_player.kitchen_sonos → playing`. State-change triggers don't fire for transitions HA wasn't observing. So whenever HA restarts (deploy, supervisor update, host reboot) and Sonos's state cycles during the restart window, the activation is silently lost.

Real-world frequencies of HA restart:

- Operator deploys (`ha/deploy.sh`): typically several per week during active development.
- HAOS Supervisor updates: monthly.
- Host VM reboots: rare but happen.

Real-world frequencies of Sonos cycling `unavailable`:

- Mesh hiccups, brief network blips: occasional.
- Caused incidentally by the HA restart itself (Sonos integration reconnects, briefly drops state): happens **every** restart with high probability.

The intersection is small per individual restart but the consequences are user-visible (override desync; tap behaviour wrong) and the recovery requires operator-side knowledge of the failure mode. Closing the hole structurally is preferable.

The same gap also bites if HA is started fresh while music was already playing — the activation is missed because no transition occurs. This isn't a new failure mode, just an under-considered cold-boot case.

## What Changes

### Automation

`ha/automations/now_playing_override.yaml` — add a new sibling automation `inkplate_sonos_ha_start_reeval`, mirroring the existing `inkplate_sonos_quiet_hours_end_reeval` (which already handles a similar "scan whether activation is missed" case at quiet-hours end). Triggered on `homeassistant.start`. Conditions:

- `media_player.kitchen_sonos == 'playing'` (only act if music is actually playing).
- `input_text.inkplate_active_override != 'now_playing'` (only act if reconciliation is needed; don't clobber prior_override when state already matches).
- Quiet-hours guard (don't activate during quiet hours).

Action body is a copy of the activation cascade from `play_start` / `quiet_hours_end_reeval`: save prior, set override, cancel linger, set content_id, publish active_mode + wake. The duplication is consistent with the existing pre-pattern; a future refactor could unify these into a script, out of scope here.

### Spec

`openspec/specs/now-playing-override/spec.md` — ADD Requirement "HA-start reconciliation" with a single Scenario.

## Impact

- **Behaviour change.** None for steady-state usage. Closes a silent failure mode after HA restarts.
- **No firmware change.** HA-side only.
- **Risk.** Low. The automation only acts when its conditions are satisfied; on a clean restart with Sonos already playing AND override correctly persisted as `now_playing`, it no-ops. On a restart where override is wrong, it converges. There is no scenario where it makes things worse.
- **Testability.** Live verification: stop ha core, edit something to force a restart, ensure Sonos is `playing` post-restart, observe override flip back to `now_playing` within seconds of HA-start.
