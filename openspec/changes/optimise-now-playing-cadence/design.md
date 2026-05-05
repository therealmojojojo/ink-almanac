# Design — Optimise Now-Playing wake cadence

## Wake-time flow

```
tick() entry
  ├── resolveSchedule() → ResolvedSchedule (existing, from add-pushable-wake-schedule)
  ├── readSessionOverride() ← NEW: read inkplate/state/active_override,
  │       update persisted.session_now_playing (empty payload = no-op)
  ├── pathForMinute(min, mode, schedule, session_now_playing):
  │       if session_now_playing OR mode == NowPlaying: return Poll  ← session-aware override
  │       …existing tier dispatch…
  │
  ├── if path == Poll:
  │     mqtt up
  │     readAndApplySchedule(...)                   ← existing
  │     readSessionOverride(...)                    ← updates session flag
  │     resolved = resolveActiveMode(...)           ← existing mode-change check
  │     if resolved != current_mode → promote to Full
  │     else if resolved == NowPlaying:             ← NOTE: mode-gated, NOT session-gated
  │         track = mqttReadRetained(now_playing_track)
  │         if track empty: skip (no signal)
  │         else:
  │             h = fnv32(track)
  │             if h != persisted.sonos_track_hash → promote to Full
  │
  ├── doFull (if reached, for any reason):
  │     …existing draw…
  │     if active_mode == NowPlaying after draw:
  │         track = mqttReadRetained(now_playing_track)
  │         if not empty:
  │             persisted.sonos_track_hash = fnv32(track)
  │
  └── plannedSleepSec uses planWake → returns Poll for session/NowPlaying minutes →
      sleep ≤60 s, next wake repeats
```

The track-hash check stays **gated on `resolved == NowPlaying`** (the current active_mode), NOT on the session flag. During a tap-peek, mode briefly flips to Summary while the session stays `now_playing`. We don't want to promote-to-Full on track changes during the peek (the user is looking at Summary). When the peek ends and mode flips back, the track-check resumes naturally.

## On-the-wire payload

Topic: `inkplate/state/now_playing_track`. Retained. Plain string (NOT
JSON). The string is whatever HA's existing helper expression yields:
the Sonos `media_content_id`, falling back to
`title|artist|album_name` joined by `|`. Empty string is a valid value
meaning "no track signal" and is treated by the device as a no-op.

The payload is opaque to the firmware — it's hashed, not parsed. So
the firmware doesn't care whether HA changes the format later, as
long as a "different track" produces "different bytes".

## Firmware: `Persisted` fields

Add to `firmware/include/wake.h`:

```cpp
struct Persisted {
  // …existing fields…
  uint32_t sonos_track_hash = 0;
  bool     session_now_playing = false;
};
```

`sonos_track_hash`: zero is the sentinel for "uninitialised / no track yet". The empty-payload short-circuit in the Poll handler ensures we never *set* the cache to a hash-of-empty-string (which would be `0x811c9dc5`, the FNV-32 offset basis), so the cached value being non-zero means "a real track was seen here previously".

`session_now_playing`: defaults to `false`. Set to `true` when `inkplate/state/active_override` retained payload is `"now_playing"`. Set to `false` for any other non-empty value (`schedule`, `weather_peek`, `summary_gallery_toggle`). **Empty payload leaves the cache untouched** — same short-circuit pattern as the schedule and track topics. The flag persists across deep sleep so a Timer wake mid-session still consults the right cadence without needing to re-read MQTT before path dispatch.

## Firmware: session-override read

A new helper, `readSessionOverride(transport)`, mirrors the schedule-read pattern:

```cpp
// In main_loop.cpp, near readAndApplySchedule:
void readSessionOverride(hal::ITransport& mqtt) {
  const auto payload = mqtt.mqttReadRetained(fw::config::kTopicActiveOverride);
  if (payload.empty()) return;            // no signal — leave cache as-is
  fw::wake::persisted().session_now_playing = (payload == "now_playing");
}
```

Called once from the main MQTT-up block in `tick()`, alongside `readAndApplySchedule`. The two reads pipeline on the same MQTT session.

## Firmware: `pathForMinute` session-aware override

```cpp
Path pathForMinute(int min_of_day, fw::modes::Mode mode, const Schedule& s,
                   bool session_now_playing) {
  if (session_now_playing || mode == fw::modes::Mode::NowPlaying) return Path::Poll;
  // …existing tier dispatch…
}
```

`planWake` gains the same parameter, threading it from the resolved persisted state at the call site. The `mode == NowPlaying` clause is the cold-boot fallback: if the override topic hasn't been read yet but `active_mode` already says now-playing, the device still gets the right cadence on its first wake. After the first MQTT read, `session_now_playing` is canonical and the mode check becomes redundant.

## Session topic on the wire

Topic: `inkplate/state/active_override`. Retained. Plain string. Values:

- `"now_playing"` — Sonos is playing AND the override is active. Device runs per-minute Poll cadence regardless of the visible face.
- `"schedule"` — no override; device follows tier cadence.
- `"weather_peek"`, `"summary_gallery_toggle"` — non-Sonos overrides; device follows tier cadence (these don't need fast cadence).
- `""` — no signal; device leaves the cached flag untouched.

The device only differentiates `"now_playing"` from everything else. New override values added in HA later (e.g., a hypothetical `"hn_peek"`) automatically fall into "tier cadence" without firmware changes.

## HA: active_override mirror

A small new automation, `ha/automations/publish_active_override.yaml` (or appended to `now_playing_override.yaml` for proximity to the state machine that mutates the input_text). Triggers on state-change of `input_text.inkplate_active_override` AND on `homeassistant.start`. Action:

```yaml
- service: mqtt.publish
  data:
    topic: inkplate/state/active_override
    payload: "{{ states('input_text.inkplate_active_override') }}"
    retain: true
    qos: 0
```

Gated by `input_boolean.inkplate_publisher_enabled` per the existing publisher convention.

## Firmware: Poll handler change

```cpp
// In main_loop.cpp, inside the Path::Poll branch, after the existing
// resolveActiveMode + mode-change-promotion block:

if (mqtt && resolved == fw::modes::Mode::NowPlaying &&
    /* mode-change-promotion didn't already fire */) {
  const auto track = h.transport.mqttReadRetained(
      fw::config::kTopicNowPlayingTrack);
  if (!track.empty()) {
    const uint32_t track_hash = fw::wake::fnv32(track);
    if (track_hash != fw::wake::persisted().sonos_track_hash) {
      // Track changed — promote this Poll to a Full. The Full path
      // updates persisted.sonos_track_hash itself; we don't pre-update
      // here so a failed Full leaves the cached hash unchanged and the
      // next Poll retries.
      doFull(h, reason, tap, local_hour, local_now, wifi, mqtt,
             /*already_resolved=*/resolved, &e);
      diag_recorded = true;
    }
  }
  // Empty payload short-circuit: do nothing, no cache write, no diag flag.
}
```

`resolveActiveMode` already runs once at the top of the Poll branch.
The track-hash check piggybacks on the same MQTT session — no extra
WiFi cost.

## Firmware: `doFull` cache update

After a successful NowPlaying draw, before returning:

```cpp
// In doFull, near the end after `wake::persisted().current_mode = active`:

if (active == fw::modes::Mode::NowPlaying && mqtt) {
  const auto track = h.transport.mqttReadRetained(
      fw::config::kTopicNowPlayingTrack);
  if (!track.empty()) {
    fw::wake::persisted().sonos_track_hash = fw::wake::fnv32(track);
  }
  // Empty: leave the cache as-is. The next Poll's empty-short-circuit
  // means we'll never spuriously promote on this state.
}
```

This closes the cold-boot trap: a freshly-flashed device that comes up
with `active_mode == now-playing` does its cold-boot Full, populates
the hash, and the next Poll sees a match.

The same hook fires on every NowPlaying Full (including the
Poll → Full promotions above), so the cache is always current after a
draw. Subsequent Polls within the same track are no-ops.

## HA: integration into the existing publisher

`ha/automations/publish_inputs.yaml::inkplate_publish_sonos` already
runs on Sonos state-change and on `media_content_id` change. Append
one action at the end of its `action:` block:

```yaml
- service: mqtt.publish
  data:
    topic: inkplate/state/now_playing_track
    payload: >-
      {{ state_attr('media_player.kitchen_sonos','media_content_id')
         or (state_attr('media_player.kitchen_sonos','media_title') ~ '|'
             ~ state_attr('media_player.kitchen_sonos','media_artist') ~ '|'
             ~ state_attr('media_player.kitchen_sonos','media_album_name')) }}
    retain: true
    qos: 0
```

Why "in the existing automation" rather than a new one: HA actions
within a single `action:` block run sequentially. The earlier action
in the same block, `rest_command.inkplate_publish_sonos`, is what
updates the renderer's `sonos.json`. By placing the MQTT publish
after the REST call, we guarantee the renderer's image is regenerated
before the device can see the new hash and decide to fetch a fresh
PNG. Two parallel automations would race; a single sequential
automation does not.

The `inkplate_sonos_track_change` automation in
`now_playing_override.yaml` does *not* need to publish the track topic
itself — it triggers `inkplate_publish_sonos` indirectly through the
Sonos state-change cascade, which now publishes the track topic. If
this is ever insufficient (e.g., a track-change that doesn't trip the
state-change trigger), we add the publish to
`inkplate_sonos_track_change` too, with the same sequencing
discipline.

## Empty-payload semantics

Mirroring the schedule topic from `add-pushable-wake-schedule`:

- A retained empty payload OR no retained value at all → device's
  `mqttReadRetained` returns empty string.
- The device SHALL short-circuit before computing FNV-32 over an empty
  string. It SHALL NOT update `sonos_track_hash`. It SHALL NOT emit any
  diag flag for "track changed". It SHALL NOT promote the Poll to a Full.
- This handles three cases uniformly: fresh broker (never seen a
  publish), Sonos-never-played (HA hasn't published yet), and explicit
  "clear" (operator publishes empty payload). All three resolve to "no
  signal, no action".

## Diag-ring observability

No new diag-ring flag bits in this change. The existing diag entry
already encodes:

- Path (`L` = Poll, `F` = Full) — operator can see which minutes were
  cheap Polls vs Full draws.
- Mode (`Y` = NowPlaying) — operator can see when the device was in
  NowPlaying mode.

A run of `tLY02 tLY02 tLY02 tFY2f tLY02 tLY02 …` in the ring is the
expected steady-state pattern: Polls (`tLY02` = mqtt-up only) with a
Full (`tFY2f` = mqtt + epd + drew + cache hit) when a track changes.

If we ever need explicit "this Poll promoted because the track hash
changed", reserve a flag bit in a follow-up change. For v1, the path
column already tells the story.

## Estimating the win

Steady-state, ~1 hour of Sonos playback, average ~12 track changes
per hour:

| | Today (Full ×60) | Proposed (Poll ×60 + Full ×12) |
| --- | ---: | ---: |
| Wakes | 60 | 60 |
| Fulls | 60 | 12 |
| Polls | 0 | 48 |
| Energy | 60 × 5 = 300 mAh | 12 × 5 + 48 × 0.5 = 84 mAh |
| Reduction | — | **~72 % cheaper** |

Even at 30 track changes per hour (continuous skipping), it's
30 × 5 + 30 × 0.5 = 165 mAh — still 45 % cheaper than today.

## Out of scope

- Reviving `kSonosFastPathSec` / `Reason::SonosFastPath`. Both
  vestigial; this change makes them more vestigial, not less. A
  follow-up cleanup change can delete them.
- Per-tier NowPlaying cadence. NowPlaying activates only outside
  quiet hours, so a single per-minute cadence is fine.
- Mid-tick track-change retargeting. The in-flight tick keeps the
  path it chose at entry; if a track change arrives mid-tick, it's
  caught on the next Poll (≤60 s later).
