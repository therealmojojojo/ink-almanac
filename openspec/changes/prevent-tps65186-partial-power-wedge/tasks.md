# Tasks

## Firmware

- [x] **F1.** Add `IDisplay::ensurePanelDown(timeout_ms = 3000)` and
  `IDisplay::readPwrGoodByte()` virtuals with safe defaults
  (`true`, `0xFA`). `firmware/include/hal/IDisplay.h`.
- [x] **F2.** Implement `ensurePanelDown` and `readPwrGoodByte` in
  `RealDisplay`: direct I²C read of TPS65186 register 0x0F, 50 ms
  poll cadence, 0xFF treated as "off." `firmware/src/hal/real/RealDisplay.h`.
- [x] **F3.** Wire `ensurePanelDown` into `doFull` just before the
  state-JSON publish; capture `epd_down_clean` + `epd_pg_raw` and pass
  to `toDeviceStateJson`. `firmware/src/main_loop.cpp`.
- [x] **F4.** Extend `toDeviceStateJson` with `epd_pg_raw` (hex string)
  and `epd_down_clean` (bool). `firmware/include/battery.h` +
  `firmware/src/battery.cpp`.
- [x] **F5.** Verify host-sim tests pass unchanged (all 98 scenarios).
- [x] **F6.** Verify ESP32 production build still links within Flash
  budget (currently 82% used; this change is ~30 LoC, no new libs).

## HA integrations

- [x] **H1.** Add MQTT sensor reading `value_json.epd_pg_raw` from
  `inkplate/state/device`. Template-friendly hex string. Entity_id
  is `sensor.inkplate_device_epd_pwr_good_raw` (HA slugified the
  friendly name; YAML-configured MQTT entities can't pin `object_id`).
  `ha/integrations/mqtt.yaml`.
- [x] **H2.** Add MQTT binary_sensor
  `binary_sensor.inkplate_device_epd_down_clean` with
  `device_class: problem`, `payload_on: "False"`, `payload_off: "True"`
  (so `on` = problem, matching the existing `epd_power_good` sensor
  convention). `ha/integrations/mqtt.yaml`.
- [x] **H3.** Add automation `inkplate_epd_down_unclean_warning` that
  fires on `binary_sensor.inkplate_device_epd_down_clean = on` for
  `00:31:00` (two consecutive Midday wakes) with a 4-hour re-notify
  throttle. Message names the raw PWR_GOOD byte for forensics.
  `ha/automations/epd_pwrgood.yaml` (alongside the existing alert;
  same notify channel).

## Spec deltas

- [x] **S1.** `openspec/changes/.../specs/device-firmware/spec.md`
  delta: add `Requirement: EPD clean-down probe`.
- [x] **S2.** `openspec/changes/.../specs/ha-integrations/spec.md`
  delta: add raw-byte sensor + predictive unclean-down requirements.

## Deploy

- [x] **D1.** Flash device over USB while it's still on the bench
  (avoids needing another battery pull). Smoke-test: serial logged
  `epd_down_clean=1 pg_raw=0x00` on the cold-boot Full wake.
- [x] **D2.** Deploy HA config via `ha/deploy.sh`. Confirmed
  `sensor.inkplate_device_epd_pwr_good_raw = "0x00"`,
  `binary_sensor.inkplate_device_epd_down_clean = off` and
  `binary_sensor.inkplate_device_epd_power_good = off` (all healthy).
- [ ] **D3.** Watch telemetry for 7 days. Record:
  - Distribution of `epd_pg_raw` values across wakes (expect almost
    all `0x00` or `0xFF`).
  - Frequency of `epd_down_clean = false`.
  - Whether any actual wedge incident is preceded by `epd_down_clean
    = false` on the prior wake.
- [ ] **D4.** Archive change once D3 yields ≥7 days of telemetry with
  no panel freeze, or if a freeze occurs, with the predictive
  `epd_down_clean = false` warning observed beforehand.

## Out of scope (tracked separately)

- Hardware load-switch MOSFET on TPS65186 VIN — the only fix that
  eliminates the failure mode entirely. Future change.
- Forking Soldered's library to extend its 250 ms cap. We chose to
  wrap above the library boundary instead.
