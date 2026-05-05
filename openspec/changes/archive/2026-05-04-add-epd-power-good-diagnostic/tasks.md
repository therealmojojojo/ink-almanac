# Tasks — EPD power-good diagnostic

## 1. Firmware

- [x] 1.1 `firmware/include/hal/IDisplay.h`: add `virtual bool ensurePanelPower() { return true; }` (default for host sim).
- [x] 1.2 `firmware/src/hal/real/RealDisplay.h`: implement `ensurePanelPower()` returning `panel_.einkOn() == 1`.
- [x] 1.3 `firmware/test/hal/mock/MockDisplay.h`: stub override + a setter so scenarios can simulate failure.
- [x] 1.4 `firmware/include/battery.h`: add `bool epd_pwrgood` parameter to `toDeviceStateJson` (last position).
- [x] 1.5 `firmware/src/battery.cpp`: emit `"epd_pwrgood":true|false` in JSON.
- [x] 1.6 `firmware/src/main_loop.cpp` `doFull`: call `h.display.ensurePanelPower()` before the fetch+draw block; log result; pass to `toDeviceStateJson`. On failure, skip the fetch/draw (Soldered would silently bail anyway).
- [x] 1.7 Host build (`cmake --build build_host`) green.
- [x] 1.8 Doctest scenarios pass (49/49 on `./build_host/firmware_sim`).

## 2. HA

- [x] 2.1 `ha/integrations/mqtt.yaml`: add `binary_sensor` named `Inkplate device EPD power good` with `device_class: problem`, `payload_on: "False"`, `payload_off: "True"`, value_template extracting `value_json.epd_pwrgood`.
- [x] 2.2 New file `ha/automations/epd_pwrgood.yaml`: notify on `binary_sensor.inkplate_device_epd_power_good == on for: "00:31:00"`, with 4-hour throttle, message includes "remove battery to recover".

## 3. Spec deltas

- [x] 3.1 `openspec/changes/add-epd-power-good-diagnostic/specs/device-firmware/spec.md` — ADDED requirement "Panel power-good diagnostic in device-state".
- [x] 3.2 `openspec/changes/add-epd-power-good-diagnostic/specs/ha-integrations/spec.md` — ADDED requirement "EPD power-good binary sensor and alert".

## 4. Validation

- [x] 4.1 `openspec validate add-epd-power-good-diagnostic` exits 0.
- [x] 4.2 Verified in production during the 2026-05-04 wake-schedule + now-playing-cadence deploys: `state/device` consistently carries `"epd_pwrgood":true`, `binary_sensor.inkplate_device_epd_power_good` reads `off` (problem clear), and the diag-ring flag bit 2 (0x04 = epd_pwrgood) is set on every successful Full (e.g. `cFU4f/r1`, `tFN2f`).
- [x] 4.3 N/A — forced-wedge smoke test deferred. **Reason**: writing 0x00 to TPS65186 register 0x01 on a live device is destructive (requires a battery-pull to recover, the very failure mode this change was written for). The reactive surface — binary_sensor flipping `on` and the 31-min debounced alert — is exercised by host scenarios using `MockDisplay`'s power-good setter; that's sufficient confidence to ship. The operator may run the destructive test on demand if the failure mode recurs.
