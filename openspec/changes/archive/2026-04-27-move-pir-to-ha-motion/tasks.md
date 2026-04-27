## 1. Firmware removal

- [ ] 1.1 Delete `firmware/src/hal/real/RealPIR.cpp` and its header; remove the include from `firmware/src/main.cpp`.
- [ ] 1.2 Delete `kPirCooldownSec` from `firmware/include/config.h` and its rationale comment.
- [ ] 1.3 Remove `last_pir_wake_epoch` from `wake::persisted()` struct; bump the persisted-state version marker if one exists.
- [ ] 1.4 Remove the PIR branch and 5-min cooldown check from `firmware/src/main_loop.cpp::tick()`.
- [ ] 1.5 Remove the PIR bit from `wake::armMask()` and drop the quiet-hours PIR-disarm branch.
- [ ] 1.6 Remove `Reason::PIR` from `firmware/include/wake.h`; update `wakeReasonToString()` and any enum switches.
- [ ] 1.7 Delete `firmware/test/scenarios/pir_cooldown_tests.cpp` (or equivalent); delete the `MockPir` harness under `firmware/test/hal/mock/`.
- [ ] 1.8 Cross-check `firmware/test/scenarios/main_loop_tests.cpp` — no scenario still asserts a `Reason::PIR` code path.
- [ ] 1.9 Rebuild host simulator: `cmake --build build -j && ./build/firmware_sim`; all remaining tests pass.

## 2. Firmware docs

- [ ] 2.1 Update `firmware/docs/wake-protocol.md`: remove `pir` from the wake-reason table; update the "Resolving active mode" and "Fast-path semantics" sections if they mention PIR.
- [ ] 2.2 Update `firmware/docs/power-budget.md`: remove PIR from the per-source Ah accounting; recompute 42-day estimate.
- [ ] 2.3 Update `firmware/docs/config.md`: remove the PIR parameter rows.
- [ ] 2.4 Update `firmware/README.md` "Main loop" section: step 3 (PIR branch) is gone; renumber.

## 3. HA — kitchen motion integration

- [x] 3.1 Operator: pair the IKEA motion sensor via the existing zigbee2mqtt bridge on the NUC (ConBee II). Friendly name `kitchen_motion_sensor` — MQTT autodiscovery surfaces it as `binary_sensor.kitchen_motion_sensor_occupancy` and `sensor.kitchen_motion_sensor_battery` in HA.
- [x] 3.2 Add `ha/automations/kitchen_motion_wake.yaml`:
  - Trigger: `binary_sensor.kitchen_motion_sensor_occupancy` `off → on`.
  - Conditions: not in quiet hours (compare `now()` against `input_datetime.inkplate_quiet_start` / `inkplate_quiet_end`, handling midnight wrap); `input_text.inkplate_active_override == schedule`.
  - Action: `mqtt.publish` to `inkplate/command/wake` with empty payload.
  - Mode: `single` with a 5-minute `throttle` (HA's `mode: single` + `max_exceeded: silent` + a time-based condition using `states.automation.kitchen_motion_wake.attributes.last_triggered`).
- [x] 3.3 Add `ha/automations/kitchen_motion_battery.yaml`:
  - Trigger: numeric state `sensor.kitchen_motion_sensor_battery` below 20.
  - Action: `notify.inkplate_operator` with body "Kitchen motion sensor battery at {{ states('sensor.kitchen_motion_sensor_battery') }}%".
  - Throttle: 24 hours (via a helper timestamp input or the same last_triggered pattern).
- [ ] 3.4 Ensure both automations are disabled by default and enabled by the operator after the sensor is paired; document in `ha/README.md`.

## 4. HA docs

- [ ] 4.1 Update `ha/docs/architecture.md`:
  - MQTT contract table: no change (the device→HA direction keeps `inkplate/state/device`; HA→device publishes `inkplate/command/wake` which already exists; this automation is just another producer).
  - Component map: add `kitchen_motion_wake.yaml` and `kitchen_motion_battery.yaml` under `automations/`.
  - State-machine section (see the documentation update landing alongside): replace device-side PIR with HA-side motion.
- [ ] 4.2 Update `ha/docs/troubleshooting.md` with a "motion not triggering wake" checklist: sensor battery, Zigbee link, automation enabled, quiet-hours window, 5-min throttle.

## 5. Spec and cross-change coordination

- [ ] 5.1 Coordinate with `add-device-firmware/tasks.md`: strike tasks 4.1–4.3 (PIR wake), mark them N/A with a pointer to this change. Do NOT archive `add-device-firmware` until this change ships, so the deletions land cleanly.
- [ ] 5.2 Verify `add-device-simulation`'s scenario catalog does not depend on removed PIR paths.
- [ ] 5.3 Link this change from `ha/docs/architecture.md`'s override-precedence section — motion is explicitly NOT a new precedence level; it's just a wake producer.

## 6. Deploy and verify

- [ ] 6.1 Flash new firmware to the device via OTA; confirm `inkplate/state/device.build` reflects the new version.
- [ ] 6.2 Deploy HA config.
- [ ] 6.3 Physically trigger the kitchen motion sensor; confirm:
  - HA's `kitchen_motion_wake` automation fires within 2 s.
  - `mosquitto_sub -t 'inkplate/command/wake'` observes the pulse.
  - Device's next natural wake (timer or fast-path) fetches the current-active-mode PNG.
- [ ] 6.4 Re-trigger motion within 5 minutes; confirm the throttle suppresses the second wake.
- [ ] 6.5 Trigger motion during quiet hours; confirm no wake is issued.
- [ ] 6.6 Simulate the battery sensor below 20% (lower the threshold temporarily or use HA's developer tools to set state); confirm the notification fires and doesn't re-fire within 24 h.
