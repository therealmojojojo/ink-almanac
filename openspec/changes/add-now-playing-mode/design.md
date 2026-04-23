## Context

Now-Playing is unique among the faces: it is the only one whose active/inactive state is driven by an external signal (Sonos playback) rather than the clock. Making it feel right requires coordinating four moving parts — HA's Sonos integration, the rendering pipeline, the device's wake mechanism, and the interaction with other overrides — without any one owning the behavior end-to-end.

This change is the thin coordination layer that stitches them together. Everything it does could technically live "somewhere else" (in HA automations, in the renderer, in the firmware), but scattering the coordination makes the behavior hard to reason about and hard to change. Giving it its own capability makes the override lifecycle a single reviewable surface.

## Goals / Non-Goals

**Goals:**
- Simple mental model: "music playing → frame shows what's playing; music stops → frame returns to the schedule after a brief linger."
- Fast response (device shows new track within ~10 seconds of playback starting or a track change).
- No flicker between back-to-back tracks, no flicker during brief pauses.
- Clear precedence order with every override.
- Quiet-hours respect — no music → frame wake during the night.

**Non-Goals:**
- Controlling Sonos from the dashboard. It's a display, not a remote.
- Showing a progress bar, elapsed time, or any time-ticking element.
- Per-service cosmetic customization (e.g., Spotify green accent). The palette is fixed.
- Multi-room Sonos awareness. Only the kitchen speaker matters. Other speakers are ignored.

## Decisions

### HA owns the activation state machine

The activation rule, linger, track-change detection, and quiet-hours suppression all live in HA automations (or Node-RED flow, or equivalent). Rationale: HA is where Sonos state lives, where helper entities are natural, where automations are easy to edit without a deploy cycle. Putting this logic in the renderer would require the renderer to poll state; putting it in the firmware would blow the thin-client architecture.

### Track-change detection by `media_content_id`

Sonos exposes a stable identifier per track. Using it is more reliable than hashing title+artist (which can collide on identically-named tracks in different albums) and more efficient than triggering on any attribute change (which fires on volume, seek, etc.). If `media_content_id` is absent for some source types, the fallback is the title+artist+album tuple.

### Album art is pre-fetched, not render-time fetched

Rationale: Sonos's `entity_picture` often points to a CDN that the Mac host can reach quickly but has latency variance. Render-time fetches would sometimes add 500ms+ to the render, pushing total latency past the 10-second freshness target. Pre-fetch on track change, let the renderer use a local path, eliminate the variance.

### Device wake is signaled by HA, not polled by the device

The device would otherwise have to poll the renderer every few seconds to discover state changes — a power-budget catastrophe. Instead, HA issues a wake signal (the firmware defines the mechanism — likely an MQTT message or a simple HTTP POST to a wake endpoint the device listens on) only when the device needs to act. This preserves deep-sleep discipline and bounds latency.

### Precedence encoded as a fixed stack

Override precedence is: Now-Playing > single-tap Weather peek > double-tap toggle > schedule. Rationale: music is a here-and-now signal the operator cares about most; Weather peek is the operator's active intent; double-tap is a persistent preference; schedule is the default. When a higher precedence override activates, the lower one is suspended; on deactivation, the lower one is restored if it's still valid (Weather peek has a 5-minute clock; double-tap persists until the next scheduled transition).

Alternative considered: precedence as a priority number per override, dynamically comparable. Rejected as over-engineering for four fixed override types.

### Quiet-hours suppression

Hardcoded window (00:00–05:00) with config override. Rationale: music playing briefly during the night (someone setting an alarm sound, a wakeup playlist, etc.) shouldn't light up the kitchen frame. The window defaults to typical sleep hours; operator adjusts if schedule differs.

Alternative considered: respect Sonos only if the current mode is not Night. Too clever; the operator might be awake and listening at 10pm when Night is active. A time-of-day window is more predictable.

### Now-Playing is inherently stateful

Unlike the scheduled faces (which are pure functions of time + inputs), Now-Playing requires remembering "is an override active?", "what was active before?", "when did linger start?" A small state machine handles this. The implementation can use HA input-helpers, but specs describe the state transitions rather than the storage mechanism.

## Risks / Trade-offs

- **Sonos entity naming.** Hardcoded `media_player.kitchen_sonos` is fragile; operator renames break the coordination. Mitigation: make it a config parameter, spec says so.

- **Source-mapping gaps.** If a new Sonos source type appears (e.g., a new streaming service), the source indicator falls back to `SONOS` alone. Mitigation: the fallback is graceful; new mappings add via a one-line config edit.

- **Latency budget.** The 10-second freshness target assumes HA, renderer, and device all behave. Any one being slow or offline breaks it. Mitigation: the scenarios specify "within 10 seconds" as a soft target, not a hard deadline. The system should still be usable with 20-second latency.

- **Linger too short / too long.** 90s defaults to conservative; on an album it's fine, on a single song followed by silence it's a noticeable pause. Mitigation: configurable, easy to tune after living with it.

- **Quiet-hours boundary race.** If music starts at 04:58 and quiet ends at 05:00, the rule as stated says activation happens at 05:00. A smart HA automation handles this; a naive one might miss the boundary. Mitigation: explicit scenario, implementer picks a polling cadence or a time-trigger to evaluate.

- **Multiple overrides stacked deep.** Conceivable: operator double-taps (toggle override) at 10am, music plays at 11am (Now-Playing over toggle), music stops at 12pm (linger, then toggle restored). The restore chain is tested via scenarios. Not a real risk, but worth noting.

## Migration Plan

No prior Now-Playing behavior exists. On apply (after `add-ha-integrations`, `add-rendering-pipeline`, and `add-dashboard-faces` are in place):

1. Define HA helper entities (the override-state holder, the linger timer, configurables).
2. Write the HA automation / Node-RED flow that watches Sonos state and implements the state machine.
3. Write the album-art pre-fetch automation (or wire it into the above).
4. Define and test the device-wake signaling path (implementer-choice: MQTT topic, HTTP POST, etc.).
5. Test each scenario from the spec end-to-end.

Rollback: disable the HA automation. Now-Playing ceases to activate; the schedule governs as if the override never existed. No other subsystem needs rollback.

## Open Questions

1. **Wake-signal mechanism.** MQTT is idiomatic in HA for device-facing signals; HTTP POST is simpler but requires the device to have a small always-listening surface. Defer to `add-device-firmware`; this change is agnostic.

2. **Source-mapping source.** Configurable via a YAML file in HA, or hardcoded in the automation? Probably YAML for easy editing. Implementation detail.

3. **Linger countdown visualization.** Should the dashboard reflect "about to revert" somehow (e.g., a subtle fade)? Probably not — a fade on e-paper ghosts and the user knows the pattern after a week. Omit unless requested.

4. **What happens when Sonos is unreachable.** If HA loses contact with the Sonos speaker mid-playback, the activation state machine sees `unavailable` rather than `idle`. Probably treat as idle (linger, revert); confirm during implementation.

5. **Per-track re-fetch of album art.** If the same album plays continuously, many tracks share the same art. Cache by URL or ignore the optimization? Likely ignore — fetches are infrequent, and the caching complexity isn't worth the microseconds.
