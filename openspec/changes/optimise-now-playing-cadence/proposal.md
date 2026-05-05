# Optimise the Now-Playing wake cadence: Poll, not Full

> **Status — 2026-05-04**: draft for discussion. No code yet.

## Why

`firmware/src/wake.cpp::pathForMinute` currently overrides every minute in
NowPlaying mode to a Full:

```cpp
if (mode == fw::modes::Mode::NowPlaying) return Path::Full;
```

A Full costs ~5 mAh (WiFi + HTTP fetch + 3-bit refresh of the entire
panel). At 60 Fulls/hour that's **~300 mAh/hour during music** — about
15% of the device's 2000 mAh budget *per hour of playback*. An evening of
music can drain the battery from full to flat. Today this is the dominant
discharge path on this device.

The *reason* the override exists is sound: the operator wants the panel
to reflect the current track within ~1 minute. But almost every one of
those 60 wakes per hour does no useful work — the track hasn't changed,
so the Full redraws an identical image. The expensive part (HTTP +
e-ink) is paid for nothing.

The cheap alternative is the same shape as `Path::Poll`: bring up
WiFi + MQTT, read a small retained payload, decide whether to redraw.
Poll costs ~0.5 mAh — **10× cheaper than a Full**. If the device
promotes to Full only on actual track change (~1 per 4–5 minutes
realistically), the per-hour cost drops from ~300 mAh to ~70 mAh,
~4× improvement, with no observable difference in panel freshness.

## What Changes

### A. New retained MQTT topic — `inkplate/state/now_playing_track`

Plain string, the same expression HA already computes for
`input_text.inkplate_now_playing_content_id`:

```jinja
{{ s.attributes.media_content_id
   or (s.attributes.media_title ~ '|'
       ~ s.attributes.media_artist ~ '|'
       ~ s.attributes.media_album_name) }}
```

Empty payload means "no track signal" — the device treats it as a no-op
(see "Empty-payload short-circuit" in `design.md`).

### B. Firmware

- `pathForMinute`: when mode is NowPlaying, return `Path::Poll` instead
  of `Path::Full`. NowPlaying still wakes every minute (same cadence as
  before); the wake just does network-only work most of the time.
- `wake::Persisted` gains a `uint32_t sonos_track_hash` field, persisted
  across deep sleep alongside `current_mode`.
- Poll handler in `main_loop.cpp`: when `current_mode == NowPlaying`,
  read `inkplate/state/now_playing_track`. Empty → skip. Non-empty →
  hash (FNV-32, same routine as the schedule). Mismatch → promote this
  Poll to a Full. Match → sleep.
- `doFull`'s NowPlaying path: after a successful draw, read the track
  topic and update `persisted.sonos_track_hash`. This closes the
  cold-boot / first-Full window where an uninitialised hash would force
  a redundant second Full.

### C. HA

The track-version publish goes into the **existing**
`inkplate_publish_sonos` automation in
`ha/automations/publish_inputs.yaml`, as the **final action** of its
`action:` block — *after* the `rest_command.inkplate_publish_sonos`
service call. HA actions are sequential within a single automation, so
this guarantees the renderer's `sonos.json` is updated before the device
sees the new hash. No new automation; no race.

Payload: the same Jinja expression already computed for the helper.

### D. Session-aware cadence override (the part that survives peeks)

The `pathForMinute` override has been keyed on `active_mode == NowPlaying`. That breaks during a tap-peek: the peek automation flips `active_mode` to Summary/Gallery for ~60 s while leaving HA's *session* state (`input_text.inkplate_active_override`) at `now_playing`. Under tier cadences with **no daytime Polls** (the operator's stated direction — Fulls + Partials only), a peek-during-music would drop the device to a 15-30 minute cadence and the peek-revert wouldn't reach the panel for that long.

Fix: key the override on the *session*, not on the current mode. HA already tracks the session via `input_text.inkplate_active_override` (peeks change mode, not session). We mirror that helper to a retained MQTT topic and let the device cache it.

- **New retained MQTT topic** — `inkplate/state/active_override`. Plain string. Values mirror the input_text: `schedule | now_playing | weather_peek | summary_gallery_toggle`. Empty payload = "no signal yet, leave cache as-is."
- **Firmware**: `wake::Persisted` gains `bool session_now_playing`. On every Full/Poll/PollPartial wake (the ones already paying for MQTT), the device reads the topic and updates the flag (true when payload == `now_playing`).
- **`pathForMinute` override** becomes:
  ```cpp
  if (session_now_playing || mode == fw::modes::Mode::NowPlaying)
    return Path::Poll;
  ```
  The `mode == NowPlaying` clause is kept as a fallback for the cold-boot window where the override topic hasn't been read yet but `active_mode` already says now-playing.
- **Track-change detection stays gated on `active_mode == NowPlaying`** (NOT session). During a peek, the user is looking at Summary; the device shouldn't promote to a Full just because the album behind the peek changed. When the peek ends, mode flips back to NowPlaying and the next Poll's track-hash check resumes.

This explicitly enables the operator's intended evening cadence: **Fulls + Partials, no Polls** outside Sonos sessions. The session flag is what keeps the per-minute Poll cadence running through peeks; without it, removing daytime Polls would make peeks unpredictable.

### E. HA — active_override mirror

Tiny new automation in `ha/automations/now_playing_override.yaml` (or a new file) triggered on state-change of `input_text.inkplate_active_override` AND on `homeassistant.start`. Action: `mqtt.publish` retained to `inkplate/state/active_override` with the input_text's current value. Gated by `input_boolean.inkplate_publisher_enabled` per the existing publisher convention.

### F. Out of scope (explicit)

- **Per-tier NowPlaying cadence** (e.g., 1 min during day, 5 min at
  night). Today NowPlaying activates only outside quiet hours
  (`inkplate_sonos_play_start` quiet-hours guard), so per-tier tuning
  is moot.
- **Track-change debouncing on the device side.** If HA's track-version
  publish flickers (e.g., Sonos exposes a transient empty
  `media_content_id` mid-stream-switch), the device promotes to Full,
  fetches whatever the renderer has, and moves on. Cheap enough that
  defensive de-flicker isn't worth the complexity.
- **Pause-during-music battery reduction.** During the linger window
  (default 90 s) the device keeps polling per-minute. The linger is
  short enough that the saving from dropping to tier cadence isn't
  worth the complexity of tracking "linger is active".
- **Restoring `kSonosFastPathSec` / `Reason::SonosFastPath`.** Both are
  vestigial today (`wake.cpp:626` literally `(void)kSonosFastPathSec;`,
  comment "redundant with daytime mode timers"). This change does not
  revive them — the per-minute Poll cadence in NowPlaying mode replaces
  whatever a fast-path would have done. A follow-up could delete the
  unused symbols.

## Why now

`add-pushable-wake-schedule` shipped today (2026-05-04) and the
operator's first observation post-deploy was that a sustained Sonos
session would burn through the battery. The fix is a small, contained
change with the same shape as the schedule-pickup path that just landed
(retained MQTT topic, FNV-32 hash dedup, Poll-promote-on-change),
making it cheap to write and review.

## Risks

1. **Race between renderer publish and MQTT publish.** Mitigated by
   appending the `mqtt.publish` step to the end of the *existing*
   `inkplate_publish_sonos` action list, so the renderer's `sonos.json`
   is current before the device can see the new hash. Sequenced, not
   parallel.
2. **Empty retained payload.** Mitigated by short-circuiting before
   hashing — same pattern as the schedule topic in
   `add-pushable-wake-schedule`.
3. **Stale-hash trap on cold boot / first Full.** Mitigated by having
   `doFull` cache the track hash before sleep when drawing a NowPlaying
   face. Subsequent Polls see a match and don't promote redundantly.
4. **Non-Sonos NowPlaying activations** (manual, debug, broken
   automation). Track topic empty → empty-payload short-circuit → no
   promotion → device stays on whatever the renderer last had. Failure
   contained to the visible content; no battery / loop blow-up.
5. **Initial Sonos-activation latency under no-daytime-Polls tiers.**
   With Fulls + Partials only, the device wouldn't otherwise pick up
   the activation (a `now-playing` retained `active_mode` update) until
   the next tier-Full — up to 30 min in midday. Mitigation: the
   operator pattern is **tap-to-activate** — a tap immediately wakes
   the device, the 2-second grace window picks up the freshly-published
   `active_mode = now-playing`, and the device draws the Now-Playing
   face within seconds. The session-aware override then keeps it on
   per-minute Poll cadence for the rest of the session. No code change
   needed; this is documented in the proposal so a future tier-tuning
   pass doesn't accidentally re-introduce daytime Polls "to fix Sonos
   latency".
6. **Active-override MQTT topic has no value at first boot.** First
   wake post-flash: the broker's retained value at
   `inkplate/state/active_override` exists (HA publishes on
   `homeassistant.start`). If HA is also down, the topic is unset →
   empty payload → short-circuit → `session_now_playing` stays false →
   device falls back to mode-based override (the `mode == NowPlaying`
   clause in `pathForMinute`). Same behavior as today. Recoverable when
   HA comes back.
