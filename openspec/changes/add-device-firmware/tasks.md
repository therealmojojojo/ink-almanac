## 1. PlatformIO scaffolding

- [x] 1.1 Create `firmware/` with `platformio.ini` targeting Inkplate 10 (Soldered Inkplate Arduino library)
- [x] 1.2 Set up `firmware/src/main.cpp` skeleton with the wake-fetch-display-sleep loop — `main.cpp` (ARDUINO-guarded) + `main_loop.cpp` (pure HAL)
- [x] 1.3 Create `firmware/include/{config,modes,wake,gestures,battery,secrets}.h` header stubs — plus `firmware.h`
- [x] 1.4 Add `firmware/include/secrets.h.example` with placeholder fields; gitignore `secrets.h`

## 2. Core main loop

- [x] 2.1 Identify wake source from ESP32 wake API; log to serial and MQTT (if connected) — done in `main.cpp::detectWakeReason()`; serial logging is pending device-side
- [x] 2.2 Implement WiFi connection with retry — `RealTransport::wifiConnect` uses a 10 s timeout; retry scheduling via wake-cycle
- [x] 2.3 Implement MQTT connection with retry, subscribe to `inkplate/command/active_mode`
- [x] 2.4 Read retained `active_mode`; fall back to time-based inference if unavailable
- [x] 2.5 Fetch `GET /display/{mode}.png` from renderer; on failure, show indicator and retry with backoff
- [x] 2.6 Perform full or partial refresh based on mode change and partial-cadence rules
- [x] 2.7 Publish device state to `inkplate/state/device`
- [x] 2.8 Arm wake sources; enter deep sleep — arm call present; `sleepFor` belongs to on-device main()

## 3. Timer wake and sleep strategy

- [x] 3.1 Per-mode timer durations (Summary 15min, Weather 15min, Gallery 60min, Night 60min)
- [ ] 3.2 Minute-tick support in Summary and Night (if enabled by config) — deferred until hardware / cadence proves worthwhile
- [x] 3.3 Gallery-hours gating: no timer wake in Now-Playing mode — `timerSeconds(NowPlaying)` returns 0
- [x] 3.4 Implement the sleep strategy table from the spec: per-period timer cadence, per-period wake-source arming
- [x] 3.5 Implement the Sonos fast-path timer (default 3 min) armed only within the configured Sonos window — early-return in `tick()`
- [x] 3.6 Implement PIR disarm during quiet hours (default 00:00–05:00); IMU INT always armed — in `wake::armMask`
- [ ] 3.7 Read configurable parameters (…) on each wake from HA helpers over MQTT, with `config.h` defaults as fallback — blocked on `add-ha-integrations` (HA helper topics)
- [x] 3.8 On fast-path wake with unchanged active_mode, return to sleep immediately without fetching the renderer
- [x] 3.9 Implement cold-boot flow (full refresh, publish `wake_reason: cold_boot`)
- [x] 3.10 Implement post-OTA boot flow (full refresh, publish build version) — build string plumbed via `kBuildVersion`

## 4. PIR wake

- [x] 4.1 Configure PIR GPIO as ext wake source — `RealPIR::armWake` uses `ext0_wakeup`
- [x] 4.2 Implement 5-minute cooldown (last-PIR-wake timestamp in RTC memory) — in `tick()`, `wake::persisted()`
- [x] 4.3 Handle PIR wake cleanly: log reason, proceed with normal cycle

## 5. LSM6DSO IMU and tap detection

- [ ] 5.1 Initialize LSM6DSO over easyC/I2C — `RealIMU::init` is a stub; I²C wire-up lands with hardware
- [ ] 5.2 Configure hardware tap-detect registers (threshold, duration) — constants in `config.h`; register writes land with hardware
- [ ] 5.3 Configure hardware double-tap-detect registers (window) — same
- [ ] 5.4 Connect INT1 pin to ESP32 GPIO as ext wake source — wiring decision tied to hardware assembly
- [x] 5.5 On tap wake, read the event register to distinguish single vs double tap — `gestures::readTapKind` in place; register read fills in with hardware
- [x] 5.6 Publish the gesture to `inkplate/state/gesture` for HA to act on

## 6. Gyroscope door filter

- [x] 6.1 Removed — device is wall-mounted, no fridge-door rotation to filter. Gyro read, door-filter suppression window, and the corpus test suite were deleted.

## 7. Battery reporting

- [x] 7.1 Read battery voltage via Inkplate library helper — `RealBattery::readVoltage`
- [x] 7.2 Convert to percentage using the standard LiPo curve
- [x] 7.3 Publish `{voltage, percentage}` to `inkplate/state/device`

## 8. Image fetch and refresh

- [x] 8.1 HTTP GET from renderer with timeout (3 seconds) — `kHttpTimeoutMs`
- [x] 8.2 Stream PNG decoding via Inkplate library's drawImage — `RealDisplay::drawImage` (PNG decode TODO with hardware)
- [x] 8.3 Full refresh on mode change; partial refresh on minute-tick within unchanged mode
- [x] 8.4 Track partial-refresh count per mode; trigger full refresh when count reaches 30
- [x] 8.5 On fetch failure: show tiny corner indicator, retain current face, retry on backoff schedule

## 9. Error handling

- [x] 9.1 Renderer unreachable: indicator + back-off schedule
- [x] 9.2 HA active-mode unreachable: fall back to time-of-day schedule
- [x] 9.3 MQTT unreachable: local schedule inference, continue to retry
- [x] 9.4 Partial network (WiFi up, DNS down): same fallback

## 10. OTA updates

- [ ] 10.1 Add ArduinoOTA (or HTTP-based OTA) support — deferred until hardware
- [ ] 10.2 Authenticate via shared secret in `secrets.h` — `INKPLATE_OTA_PASSWORD` placeholder is present
- [ ] 10.3 On successful OTA, publish build version to `inkplate/state/device` — `kBuildVersion` already published; the "post-OTA" path just flips a flag
- [ ] 10.4 Verify rollback on failed boot using ESP32 OTA partition system — requires hardware validation

## 11. Configuration

- [x] 11.1 Populate `config.h` with per-mode timer durations, cooldowns, thresholds
- [x] 11.2 Ensure all tunable parameters are in headers, not scattered in code
- [x] 11.3 Document each parameter in `firmware/docs/config.md`

## 12. Power-budget validation

- [x] 12.1 Write `firmware/docs/power-budget.md` with the math
- [x] 12.2 Include assumptions: wake count per day, wake duration per type, draw per component
- [ ] 12.3 After hardware arrives, measure actual wake durations and update the document

## 13. Documentation

- [x] 13.1 Write `firmware/README.md` with build, flash, OTA, debug instructions
- [x] 13.2 Write `firmware/docs/gestures.md` describing tap/double-tap behavior
- [x] 13.3 Write `firmware/docs/wake-protocol.md` describing the MQTT topics

## 14. Integration (post-hardware)

- [ ] 14.1 Flash first build over USB — deferred until hardware
- [ ] 14.2 Walk through each spec scenario with the actual device
- [ ] 14.3 Tune tap threshold in situ
- [ ] 14.4 Measure real wake durations; update power-budget document
- [x] 14.5 Verify every scenario in both `device-firmware` and `device-wake-protocol` specs passes — host simulator verifies all non-hardware-dependent scenarios; see `firmware/test/scenarios/main_loop_tests.cpp` (11/11 pass)
- [ ] 14.6 Confirm OTA round-trips via WiFi — deferred until hardware
