## Why

The original device-firmware design treated every wake as a full fetch-and-refresh cycle. To keep the clock visibly correct, this meant either (a) waking every minute and paying a full network round-trip each time — roughly 1 A·h/day, untenable — or (b) waking rarely and tolerating a clock that's up to an hour stale. Neither is good.

The architecture conversation surfaced a third path: **let the clock be a local render, not a fetched one.** The device already has accurate time (NTP on boot, PCF85063A-backed RTC); shipping digit glyphs in firmware flash is cheap; e-ink supports partial-refresh of a sub-region without the black-flash of a full refresh. Put together: minute-tick locally, full-fetch periodically.

This change ratifies that model, and with it a handful of closely-related UX refinements that cluster around the same wake loop: approximate-time phrasing on the Night face (no more precise clock there — a poetic surface shouldn't pretend to second-level precision), a bottom-left status-glyph slot for transient indications (tap acknowledged, fetch failed), and the use of the on-board PCF85063A external RTC as the primary time source so the clock survives main-battery power events.

## What Changes

- **Local minute-tick rendering.** During the day (06:30–22:00), the device wakes every 1 minute, reads the PCF85063A RTC, draws the clock glyphs into the clock zone from firmware-shipped bitmap fonts, and performs a partial refresh of just that rectangle. No WiFi, no MQTT, no HTTP on a minute-tick wake. During the night (22:00–06:30), the same mechanism fires at :00 / :15 / :30 / :45 with the approximate-phrase text instead of digits.
- **Periodic full fetches, decoupled from minute-tick.** Full network cycles run on a slower cadence (Day 15 min, Night 60 min), plus schedule boundaries, taps, and HA wake pulses. Full cycles paint the whole face (which also refreshes the clock zone authoritatively). The ghost-clear cadence (every 30 partials) still applies and promotes a local-tick wake to a full refresh when it fires.
- **Approximate-time phrasing on Night.** Night face replaces the precise `HH:MM` stacked clock with a four-phrase table keyed to 15-minute quarters: `"{H} o'clock"`, `"quarter past {H}"`, `"half past {H}"`, `"quarter to {H+1}"`. The same algorithm runs in the renderer (for full fetches) and in the firmware (for local 15-min ticks) so they always agree.
- **Clock-zone contract.** Each face declares a clock-zone rectangle in panel coordinates. The renderer exposes `GET /display/zones.json`; firmware fetches it at cold boot, caches a last-known-good snapshot in flash for offline boots, and uses it to know which rectangle to partial-refresh.
- **Top-right status-glyph slot, overlapping the battery indicator.** The existing battery-indicator area in the top-right corner doubles as the transient-status slot: when a status glyph is active, the firmware partial-refreshes over the battery indicator; when the glyph clears (on the next full refresh), the battery indicator is repainted. Two glyphs initially: `ack` (thumbs-up bitmap, appears on IMU wake, clears on next full refresh) and `error` (⚠ bitmap, appears on fetch failure, clears on next successful fetch). This keeps all chrome in one corner and avoids reserving a new pixel-clean region.
- **PCF85063A as primary clock source.** Firmware uses the on-board external RTC (which stays ticking from the CR2032 coin cell through main-battery power events) instead of the ESP32 internal RTC, and syncs it from NTP after each successful WiFi bring-up.
- **New wake reason `Reason::LocalTick`.** Distinct from `Reason::Timer` so the firmware main-loop and the simulator can branch cleanly between "local partial draw only" and "full fetch cycle."
- **Tap is a wake signal, not a policy decision.** Firmware publishes the raw gesture (`{ kind: single | double }`) to `state/gesture` and reads retained `active_mode`; HA's override-precedence state machine owns the decision of what the gesture means. To bound tap-to-face-change latency, the firmware waits up to 2 s after publishing for an updated `active_mode` before committing to the fetch.

## Capabilities

### Modified Capabilities

- `device-firmware`: new local-tick rendering path, new wake reason, new cadence table, new status-glyph behavior, external-RTC primary clock, modifications to the thin-client main loop and the sleep strategy.
- `device-wake-protocol`: local-tick wakes do NOT publish `state/device` (they'd be noise at 930/day). State publishing remains on full-cycle wakes only.
- `dashboard-faces`: clock-zone coordinate contract per face, Night face switches to approximate phrasing.
- `rendering-pipeline`: adds `GET /display/zones.json` endpoint; Night face clock input becomes a phrase computed via a shared algorithm.

### New Capabilities

None. This change composes existing capabilities.

## Impact

- **Firmware** — new local-clock render path (`src/clock_local.cpp`), bitmap fonts (`src/assets/fonts/`), night phrase table (`src/night_phrases.cpp`), `Reason::LocalTick`, PCF85063A integration.
- **Renderer** — `GET /display/zones.json`, Night face approximate-phrase computation aligned with firmware, font pin so firmware bitmap generation tracks renderer typography.
- **Build step** — TTF-to-`GFXfont` codegen from renderer fonts so firmware glyphs match renderer typography; runs as part of firmware build.
- **Power budget** — revised target. Local-tick wakes ~0.025 mAh each; full-cycle wakes ~1.08 mAh each. Day: 930 × 0.025 + 62 × 1.08 ≈ 90 mAh; Night: 34 × 0.025 + 8 × 1.08 ≈ 10 mAh (if we keep night ticks; cheaper if we drop them). Estimated total ~115 mAh/day with some margin — above the original 87 mAh/day target, below the 180+ mAh/day option-A polling path. Acceptable.
- **Simulator** — new scenarios for local-tick paths, status-glyph emission, external-RTC fallback, zones.json bootstrap fallback.
- **Docs** — `firmware/docs/wake-protocol.md`, `config.md`, `power-budget.md`, and `ha/docs/architecture.md` all carry the updated cadence table.
- **Dependencies** — assumes `add-device-firmware §5.4` (LSM6DSO INT1 → RTC-domain GPIO) lands; if it doesn't, the local-tick cadence still works, tap response just degrades to polling-bound latency.
- **Supersedes** — the "minute-tick fetches full PNG and partial-refreshes minute region" rule in `add-device-firmware`'s original "Thin-client main loop". The 5× timer-tightening tuning pass (all timers at 60 s in `config.h`) is rolled back; cadence is explicitly split between local and full paths.
