# Fix `resolveActiveMode` time-of-day fallback firing during steady-state MQTT hiccups

> **Status — 2026-05-05**: implementation in this change directory; OTA flash pending.

## Why

Live diagnosis on 2026-05-05 of an "active_mode briefly flips to weather during a now-playing session" bug:

```
diag (epoch_low values, latest 32 wakes during active Sonos session):
  ... 1f7c,tLY2f 1fa8,tLY23 1fb7,tLY2f 1fe5,tLW2f 201f,tLY33 ...
       ^drew Y    ^cheap     ^drew W    ^drew Y     ^started Y again
                  Poll       (rogue)    (revert)
```

`commanded_face` (HA's mirror of the retained `inkplate/command/active_mode` topic) **never** transitioned to `weather` during the session. A 16-minute MQTT capture across the next /15 boundary saw zero `weather` publishes to that topic. HA's automation traces show the alternation tick correctly evaluating `override == schedule` to `False` and skipping the publish. Yet the device reliably and repeatedly drew Weather.

Root cause traced to `firmware/src/main_loop.cpp::resolveActiveMode`:

```cpp
fw::modes::Mode resolveActiveMode(hal::ITransport& mqtt, int hour) {
  auto payload = mqtt.mqttReadRetained(fw::config::kTopicActiveMode);
  if (!payload.empty()) {
    auto m = parseModePayload(payload);
    if (m != fw::modes::Mode::Unknown) return m;
  }
  return timeOfDayFallback(hour);   // ← weather between 10:00 and 22:00
}
```

`mqttReadRetained` is implemented as an 800 ms blocking subscribe wait. On a marginal RSSI link (the device sat at -76 dBm during this episode) the broker's retained-value delivery sometimes doesn't land in 800 ms. When it doesn't, `mqttReadRetained` returns empty → `resolveActiveMode` falls through to `timeOfDayFallback(hour)` → at hours 10-22 that returns `Weather`. The Poll-Full path then "promotes" the wake (because `Weather != current_mode`), draws Weather, and updates `current_mode = Weather`. The next Poll's read usually succeeds, sees `now-playing`, promotes again, draws NowPlaying.

This pattern is happening **multiple times per session**, not just at /15 alternation ticks (the alignment we'd hypothesized initially was coincidence). It's a steady-state MQTT-jitter bug, not a publish bug.

## What Changes

`resolveActiveMode` SHALL distinguish two empty-payload cases:

1. **Cold-boot, before HA has populated `active_mode` retained** — the original case the time-of-day fallback was designed for. `wake::persisted().current_mode == Mode::Unknown`. Use the time-of-day fallback.
2. **Steady-state MQTT hiccup** — `current_mode` is already populated (we know what we drew last) and the broker just didn't deliver the retained value within the 800 ms window. **Use the persisted `current_mode`**, NOT the time-of-day fallback. A transient broker-delivery delay should not invent a face change.

Patch (firmware/src/main_loop.cpp):

```cpp
fw::modes::Mode resolveActiveMode(hal::ITransport& mqtt, int hour) {
  auto payload = mqtt.mqttReadRetained(fw::config::kTopicActiveMode);
  if (!payload.empty()) {
    auto m = parseModePayload(payload);
    if (m != fw::modes::Mode::Unknown) return m;
  }
  // Empty payload. If we already know what we're rendering (post-cold-boot
  // steady state), trust persisted current_mode rather than inventing a face
  // from time-of-day — that fallback was meant for the genuine "HA hasn't
  // published yet" cold-boot case, not for transient broker-delivery delays
  // on a marginal RSSI link.
  if (wake::persisted().current_mode != fw::modes::Mode::Unknown) {
    return wake::persisted().current_mode;
  }
  return timeOfDayFallback(hour);
}
```

## Capabilities

### Modified Capabilities

- `device-firmware` — Active-mode discovery: clarify that the time-of-day fallback applies *only* when `current_mode == Unknown` (cold boot before any successful Full).

## Impact

- **Battery**: no change. The path runs the same number of MQTT round-trips.
- **First-boot behavior**: unchanged. `current_mode` starts at `Unknown` until the first successful Full draw, so the first-boot fallback still fires when needed.
- **Network-down behavior**: when MQTT is genuinely down, `mqttConnect()` returns false and the Poll path bails before reaching `resolveActiveMode` — the relevant scenario is "boot with network unreachable" which uses the same fallback for the cold-boot case (see `device-firmware` "Boot with network unreachable" scenario).
- **Sonos sessions**: the rogue weather draws stop. The user-visible result: Now-Playing stays on screen across the whole session, except for the deliberate 60-s peek-after-tap or for a real schedule transition.
- **No HA-side changes**. The bug was misattributed to HA earlier in the diagnosis; this change is firmware-only.

## Risks

1. **Stale `current_mode` if HA legitimately changed `active_mode` but the device's read times out for many wakes in a row.** Mitigated by: the next Poll's read succeeds (most wakes do, only a fraction of marginal ones fail), at which point the legitimate change is picked up. The previous behavior drew a *wrong* face during the same hiccup; the new behavior just draws the *previous* face for one extra wake. Strictly better.
2. **Cold-boot regression**: if the cold-boot first-Full path doesn't initialize `current_mode` correctly, the new branch could return Unknown. Mitigated by: the existing cold-boot path explicitly sets `current_mode` after a successful first draw, and the host tests cover this.
