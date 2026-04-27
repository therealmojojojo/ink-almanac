## Why

The original architecture placed a PIR sensor on the device: a GPIO wake source with a 5-minute RTC-memory cooldown. That decision predates the operator's choice of an IKEA VALLHORN/motion sensor reporting directly to HA over Zigbee/Matter. Keeping the device-side PIR would mean wiring a discrete PIR to the Inkplate, calibrating it, and burning battery on a wake path that HA-side motion would serve equally well — while the IKEA sensor is already physically better-placed (stuck to a cabinet), better-calibrated (factory), and its battery is user-replaceable (CR2032).

This change relocates motion detection entirely to HA. The device loses a wake source; HA gains an automation that translates `binary_sensor.kitchen_motion_sensor_occupancy` transitions into `inkplate/command/wake` pulses. The device's 5-minute cooldown becomes an HA `throttle`. The "PIR disarmed during quiet hours" rule becomes a condition on the HA automation. The `Reason::PIR` enum entry becomes unused and is removed from the wake-protocol contract.

## What Changes

### Device firmware

- Remove the PIR wake source from `device-firmware`'s Sleep-strategy table — drop the "PIR armed" column; drop the 5-min PIR cooldown scenarios; drop the "Quiet-hours PIR disarm" scenario.
- Remove `wake_reason: pir` from the published `inkplate/state/device` enum; `ha_command` already covers motion-triggered wakes indistinguishably.
- Delete `firmware/src/hal/real/RealPIR.*`, `firmware/src/wake.cpp::armPirWake()`, `kPirCooldownSec` from `config.h`, and the `last_pir_wake_epoch` field from `wake::persisted()`.
- Delete PIR-related tasks 4.1–4.3 and PIR-related test scenarios under `firmware/test/scenarios/`.

### HA

- Add the IKEA motion sensor to HA via the existing zigbee2mqtt bridge on the NUC (ConBee II coordinator). Friendly name `kitchen_motion_sensor`; MQTT autodiscovery produces `binary_sensor.kitchen_motion_sensor_occupancy` + `sensor.kitchen_motion_sensor_battery` + an illuminance-threshold binary_sensor (the newer E2134 model carries a lux reading).
- Add `ha/automations/kitchen_motion_wake.yaml`:
  - **Trigger**: `binary_sensor.kitchen_motion_sensor_occupancy` `off → on`.
  - **Conditions**: not within quiet hours (`input_datetime.inkplate_quiet_start`–`inkplate_quiet_end`); `input_text.inkplate_active_override == schedule` (motion does not preempt a live override); throttle of 5 minutes (same semantic as the removed device cooldown).
  - **Action**: publish `inkplate/command/wake` (no payload). The device's next natural or fast-path wake picks up `active_mode` from the retained topic.
- Add a low-battery notification for the IKEA sensor itself (`sensor.kitchen_motion_sensor_battery`), mirroring the existing device low-battery rule: notify at <20%, 24-hour throttle (coin-cell batteries drain slowly; no need for the device's 4-hour cadence).

### Wake-protocol spec

- Shorten the `wake_reason` enum: remove `pir`. `ha_command` remains the catch-all for HA-initiated wakes (motion, schedule, now-playing).

## Capabilities

### Modified Capabilities

- **`device-firmware`** — Wake sources and Sleep strategy requirements drop PIR.
- **`device-wake-protocol`** — wake-reason enum loses `pir`.
- **`ha-integrations`** — adds a Motion-wake requirement and a PIR-sensor-battery notification requirement.

### New Capabilities

None.

## Impact

- **Firmware LOC**: net negative — RealPIR/PIR cooldown paths and tests go away. The host simulator loses its `MockPir` harness; test scenarios for PIR cooldown are deleted.
- **Power budget**: marginally better — one fewer wake source to arm/disarm per sleep entry. The motion-triggered wake latency is still bounded by the device's timer/fast-path cadence (up to 60 min on Gallery, 15 min on Summary, 3 min on Sonos fast-path), which is no worse than the previous on-device PIR-with-5-min-cooldown semantics.
- **Hardware**: one fewer component to wire. The device BOM loses the PIR module and its GPIO connection.
- **Responsiveness**: functionally equivalent. The on-device PIR would have woken the device directly, but still subject to the 5-min cooldown; HA-triggered wake only arrives at the next timer/fast-path wake (up to 3 min on Sonos fast-path during daytime, up to the mode timer otherwise). For an ambient display, this is acceptable — the operator will rarely notice the difference.
- **Docs**: `firmware/docs/wake-protocol.md` loses PIR rows; `ha/docs/architecture.md` gains the motion-wake row in its MQTT contract and component map.
- **Does not change**: the HA→renderer input bridge, the pairing pipeline, the corpus, the dashboard faces.
