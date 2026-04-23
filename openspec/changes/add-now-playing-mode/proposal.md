## Why

The dashboard's base schedule (Summary 06:30–10:00, Gallery 10:00–22:00, Night 22:00–06:30) describes the resting state of the frame. But when music is playing on the kitchen Sonos, the operator wants the frame to reflect that — with album art, track info, and source indicator — regardless of the scheduled mode.

Making this work end-to-end requires coordination across three subsystems: Home Assistant (which owns the Sonos entity state), the rendering pipeline (which renders the Now-Playing face), and the device (which must be woken to display the new render). None of the other change proposals own this coordination; without it, Now-Playing remains an unconnected face.

## What Changes

- Introduce the **override mechanism**: Now-Playing preempts the scheduled face whenever `media_player.kitchen_sonos.state` is `playing`. When playback ends, the face lingers for a configurable duration (default 90s) before reverting to the schedule. The 90s linger absorbs between-track pauses so the face doesn't flicker back to Summary mid-album.
- Implement **track-change detection**: the HA-side logic identifies a new track by `media_content_id` (or equivalent stable attribute) and signals the renderer + device only on true track changes, not every attribute update.
- Implement **album-art preparation**: on track change, HA fetches the Sonos `entity_picture` to a local path on the Mac host, the rendering pipeline pre-dithers it, and the rendered Now-Playing PNG becomes available at `/display/now-playing.png` before the device is woken.
- Implement **device wake on Now-Playing entry and track change**: HA issues a wake signal to the Inkplate (via the device's wake endpoint, defined by `add-device-firmware`) so the frame updates without waiting for the next scheduled check-in.
- Define the **precedence order** between Now-Playing and other overrides (single-tap Weather peek, double-tap Summary/Gallery toggle): Now-Playing has the highest precedence during active playback; when playback ends, the override that was in effect before Now-Playing began is restored if still valid, otherwise the schedule takes over.
- Define the **cross-mode idle rule**: when Sonos is idle AND no other override is active, the schedule governs as normal.
- Implement **Now-Playing suppression during deep-night**: between 00:00 and 05:00, Sonos playback does NOT trigger Now-Playing (rare case, but the frame should stay in Night mode during sleep hours even if music plays briefly). This is an operator-configurable default.

## Capabilities

### New Capabilities

- `now-playing-override`: The coordination that turns Sonos state into a rendered, displayed Now-Playing face — activation rule, track-change detection, album-art preparation, device wake signaling, linger behavior, and precedence against other overrides.

### Modified Capabilities

None. This change consumes `dashboard-faces` (the layout), `rendering-pipeline` (the PNG generation), and will consume `ha-integrations` (the Sonos entity setup) and `device-firmware` (the wake endpoint), but does not modify any of them.

## Impact

- **New HA automation**: triggered on Sonos state changes, handles track-change detection and wake signaling.
- **New album-art staging location**: a local path on the Mac host (e.g., `renderer/staging/now-playing/current.jpg`) that the renderer reads when building the Now-Playing face.
- **New state coordination**: a small piece of state (the "currently-active override") needs to be tracked somewhere — likely an HA helper entity. The choice of state-holder is an implementation detail; the behavior is specified here.
- **No new dependencies** beyond what HA and the renderer already provide.
- **No firmware changes in this proposal**: the device's wake endpoint is defined by `add-device-firmware`; this change only specifies what calls it and when.
