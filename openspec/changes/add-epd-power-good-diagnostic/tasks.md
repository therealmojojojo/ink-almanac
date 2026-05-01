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
- [ ] 4.2 Flash firmware (`pio run -e inkplate10 --target upload`) and `ha/deploy.sh`; confirm `"epd_pwrgood":true` appears in `inkplate/state/device` after the next Full and that `binary_sensor.inkplate_device_epd_power_good` reports `off` in HA.
- [ ] 4.3 (Optional smoke) Force a wedge by writing 0x00 to TPS65186 register 0x01 mid-run and confirm the binary_sensor flips and the alert fires after the 31-min debounce window.
