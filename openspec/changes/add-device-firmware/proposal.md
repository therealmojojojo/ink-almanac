## Why

The Inkplate 10 is the physical end of the system: it is what the operator sees on the fridge. Until firmware is written and flashed, every other capability is server-side abstraction. This change is what turns the dashboard into a thing that hangs on a fridge.

The survey of state-of-the-art e-paper projects (MagInkDash, HomePlate, lmarzen, TRMNL) converges on a pattern: server renders the PNG, device fetches it, device displays it, device sleeps. The firmware is thin. This proposal ratifies that pattern for our device and specifies the wake/sleep/gesture behaviors that the rest of the system assumed.

## What Changes

- Introduce the `firmware/` directory in the repo with a PlatformIO project targeting the Inkplate 10 using the Soldered Inkplate Arduino library.
- Implement the **thin-client loop**: wake → fetch active mode URL → drawImage → sleep. No on-device layout, no on-device fonts, no on-device rendering beyond PNG display.
- Ratify a **unified sleep strategy** specifying per-mode timer cadence, per-hour wake-source arming (PIR disabled during quiet hours), and a 3-minute Sonos fast-path polling timer during Sonos-eligible hours so Now-Playing activation latency is bounded without an always-listening companion device.
- Implement **wake sources**: timer (for scheduled refreshes and minute tick during Night/Summary where applicable), PIR (motion), LSM6DSO INT pin (tap events), HA-triggered wake (MQTT retained state observed on each natural wake), and the Sonos fast-path timer.
- Implement **active-mode discovery**: on wake, the device asks HA (or a small HA-exposed endpoint) which mode is currently active, then fetches that mode's PNG. Avoids hard-coded schedule duplication on the device.
- Implement **tap detection** via LSM6DSO INT pin (hardware tap detection, not polling). Single-tap → Weather peek. Double-tap → Summary/Gallery toggle.
- Implement **battery reporting**: read battery voltage via Inkplate's built-in divider; publish percentage and voltage to HA on each wake.
- Implement **deep-sleep discipline**: after each full-refresh cycle, enter deep sleep with only the configured wake sources armed. Target active-hours power budget: <30 seconds of wake per hour on average.
- Implement **ghosting-clear cadence**: after every N partial refreshes (default 30), do a full refresh to clear ghosting before resuming partial refresh (for Summary minute tick and Night minute tick).
- Implement **linger-on-full-frame**: when fetching a new mode PNG, always do a full refresh. Partial refresh applies only within a mode for minute-region updates.
- Implement **error-handling modes**: if the renderer is unreachable, display a small "unavailable" indicator (tiny placeholder) rather than blanking or panicking; keep trying with back-off.
- Implement **OTA update support** for firmware updates over Wi-Fi.
- Implement **config via secrets.h.example**: WiFi credentials, renderer URL, HA URL, wake-endpoint details all in `firmware/include/secrets.h` (gitignored; example committed).

## Capabilities

### New Capabilities

- `device-firmware`: The on-device software — thin-client loop, wake/sleep discipline, gesture detection, power budgeting, OTA, error handling.
- `device-wake-protocol`: The contract for how HA signals the device to wake outside its scheduled timer (MQTT topic or HTTP endpoint). Split from `device-firmware` so HA and firmware specs can coordinate on it explicitly.

### Modified Capabilities

None. This change implements the device side of contracts ratified by `add-rendering-pipeline` (PNG URLs), `add-ha-integrations` (active-mode endpoint, low-battery notification), and `now-playing-override` (wake signal).

## Impact

- **New directory**: `firmware/` with `platformio.ini`, `src/main.cpp`, `include/{config,modes,wake,gestures,battery,secrets}.h`, `include/secrets.h.example`.
- **New dependencies**: Soldered Inkplate Arduino library, LSM6DSO driver library, PIR sensor library (trivial), an MQTT client library (if MQTT is chosen for wake).
- **Hardware** (ordered but not yet arrived — this change ratifies firmware design without blocking on hardware): Inkplate 10, 5000mAh LiPo, LSM6DSO IMU breakout, PIR sensor breakout, Qwiic cables, USB-C panel-mount extension.
- **Flashing workflow**: USB-connected during firmware development; OTA after initial flash. Documented in `firmware/README.md`.
- **Power budget commitment**: target 6+ weeks between charges on the 5000mAh battery under normal use; spec includes the math.
- **Consumes**: `/display/{mode}.png` from the renderer, HA's active-mode endpoint, HA's wake signaling mechanism.
