# Tasks — Fix `resolveActiveMode` time-of-day fallback during MQTT hiccups

## 1. Firmware

- [x] 1.1 `firmware/src/main_loop.cpp::resolveActiveMode`: when `mqttReadRetained` returns empty AND `wake::persisted().current_mode != fw::modes::Mode::Unknown`, return `current_mode` instead of falling through to `timeOfDayFallback(hour)`. Add a comment block explaining the cold-boot vs. steady-state distinction.
- [x] 1.2 `firmware/include/firmware.h`: bump `kBuildVersion` to `0.8.1-active-mode-fallback`.

## 2. Test

- [x] 2.1 New test case in `firmware/test/scenarios/main_loop_tests.cpp`: cold-boot into a non-default mode, then issue a Timer wake with empty retained `active_mode`. Assert that `fullRefreshCount` does not increment (no mode-change-promotion happened) — which is only true if the new fallback kicks in. Without the fix this test would fail because `resolveActiveMode` would return Weather and trigger a Full.
- [x] 2.2 Verify existing cold-boot tests still pass — the path with `current_mode == Unknown` falls back to time-of-day, same as before.

## 3. Spec delta

- [x] 3.1 `openspec/changes/fix-active-mode-fallback/specs/device-firmware/spec.md` — MODIFIED Requirement: Active-mode discovery. Add the cold-boot vs. steady-state distinction explicitly, with a scenario for each.

## 4. Validation

- [x] 4.1 `openspec validate fix-active-mode-fallback` exits 0.
- [x] 4.2 Host build green, `cd firmware && cmake --build build_host -j && ./build_host/firmware_sim` exits 0 with all tests passing.

## 5. Deployment

- [x] 5.1 USB-flash the device (`pio run -e inkplate10 -t upload --upload-port /dev/cu.usbserial-220`). Confirmed via retained `inkplate/state/device.build == 0.8.1-active-mode-fallback`.
- [x] 5.2 Live verification: start a Sonos session, observe diag for 10+ minutes. The pattern of `tLY → tLW → tLY` flips that we saw before the fix should not recur. The diag ring should stay solidly in `tLY…` (Polls + partial clock ticks) with Fulls only on actual track changes or peek/peek-revert.
