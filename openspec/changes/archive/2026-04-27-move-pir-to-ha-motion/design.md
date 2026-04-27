## Context

The sleep-strategy design in `device-firmware` treats PIR as one of four wake sources, alongside timer, IMU INT, and HA wake. The justification was self-sufficiency: if HA is unreachable, the device can still respond to presence. But the quiet-hours rule means PIR is already disarmed for ~5 hours a day; the 5-min cooldown means PIR is debounced in a way that would be trivial to do in HA; and the hardware/calibration overhead for a custom PIR is real.

The operator now has a battery-powered IKEA motion sensor directly reachable by HA's Zigbee stack. Moving motion detection to HA costs responsiveness (up to `fast_path_interval` seconds of latency during Sonos hours, up to `timer` seconds otherwise) and buys: no custom PIR calibration, no device GPIO budget spent, no RTC-memory bookkeeping for cooldowns, no firmware branch for the disarm-during-quiet-hours rule. For an ambient kitchen display, the responsiveness trade is acceptable.

## Goals / Non-Goals

**Goals:**

- Eliminate the device-side PIR path entirely — code, config constants, RTC state, spec requirements.
- Preserve the *behavioral* outcome: "someone walks into the kitchen during a non-quiet hour → the face updates reasonably soon," within the latency bounds the sleep strategy already accepts for other HA-initiated wakes.
- Mirror the IKEA sensor's low-battery reporting into HA's existing notification path.

**Non-Goals:**

- Zero-latency motion wake. The device cannot receive MQTT while in deep sleep; that premise was already acknowledged by `device-wake-protocol` Option B. Motion-triggered wakes arrive at the next natural device wake.
- Replace the IMU INT (tap) wake. Tap is a separate UX gesture, still valuable, still on-device, still governed by the gyroscope door filter.
- Multi-room presence. The IKEA sensor covers the kitchen; extending to other rooms is out of scope here.

## Decisions

### Wake latency is acceptable at motion → mode-timer bound

On-device PIR previously woke the device immediately (subject to cooldown). HA-side motion wakes via `inkplate/command/wake`, which the device observes on its *next natural wake*. During Sonos active hours (07:00–20:00 default), the fast-path timer bounds that to 3 minutes. Outside that window, it's the mode timer: 15 min in Summary/Weather, 60 min in Gallery/Night.

The worst case is someone entering the kitchen at 21:15 during Gallery — motion fires, HA pulses wake, device won't observe until the next 60-min timer wake, which could be 59 minutes away. But Gallery is the "ambient" mode by design; someone entering the kitchen isn't expecting the display to react. Accepted.

If responsiveness ever becomes a problem, the fix is to shorten the Gallery timer or extend the Sonos fast-path window, both edits to helper defaults, not a code change.

### Motion does not preempt overrides

The motion automation runs only when `active_override == schedule`. Rationale: during a Weather peek or while Now-Playing is live, motion shouldn't force a refresh — the user already chose what's on the display. This matches the existing override-precedence rule.

### Cooldown moves to HA throttle

The device's 5-min `kPirCooldownSec` becomes a 5-min `throttle` clause in the HA automation. Semantically identical. A benefit: the throttle persists across HA restarts via `homeassistant.on_start`, whereas the device's RTC-memory would lose the stamp on any cold boot.

### Quiet hours move to HA condition

The device's `quiet_start`/`quiet_end` helpers are still published over MQTT for the *fast-path* strategy (still valid), but the motion automation reads the helpers locally on HA rather than reading back from the retained topic. Same values, two readers.

### IKEA sensor battery

The VALLHORN (and similar IKEA motion sensors) exposes `sensor.<name>_battery` as a percentage via the IKEA integration. Mirror the existing `low_battery.yaml` automation: notify at <20%, throttle 24h. The CR2032 in these sensors typically lasts 1–2 years; a 4-hour re-notify throttle would be noisy for such a slow-draining source.

## Risks / Trade-offs

- **IKEA sensor unreachable.** If the Zigbee/Matter link drops, motion-wake stops firing. The device's timer/fast-path wakes still run, so the display doesn't get stuck — it just won't react to motion. No additional failure-handling code needed.
- **Motion-wake storms.** If the IKEA sensor misfires repeatedly, HA's 5-min throttle caps the wake rate to once per 5 minutes. Matches the previous on-device cooldown.
- **User confusion during transition.** Someone used to "wave at the fridge → display refreshes in < 1 s" will see up to 3 minutes of latency during daytime. Document in `ha/docs/architecture.md` that motion is now a "soft" wake source.
- **Deleting working firmware code.** The PIR HAL is skeletal (task 4.x are mostly stubs per `add-device-firmware/tasks.md`), so we're removing stubs plus a small RTC-memory field and two tasks. Low risk. Test scenarios for PIR cooldown in `firmware/test/scenarios/` are also deleted — they were verifying a behavior that no longer exists.

## Migration Plan

On apply:

1. Ship the firmware change: delete PIR HAL, drop `kPirCooldownSec`, drop `last_pir_wake_epoch` from persisted state, shorten `wake_reason` enum. Bump firmware version.
2. Ship the HA change: add `kitchen_motion_wake.yaml` and `kitchen_motion_battery.yaml`, new sensor configured via the operator's existing IKEA integration.
3. Flash the new firmware before or in parallel with the HA deploy — the retained `inkplate/state/device.wake_reason` vocabulary is device-controlled, so HA simply won't see `pir` again after flash.
4. Verify: trigger motion physically, confirm HA logs the wake publish, observe the device's next natural wake fires a `/display/*.png` fetch with the updated `active_mode` if it changed.

Rollback: restore the firmware commit (PIR HAL + cooldown field), drop the two HA YAML files, keep the IKEA sensor configured (harmless). This is a reversible but non-trivial rollback because it touches firmware; prefer forward-fix.

## Open Questions

1. **Exact IKEA entity name.** Resolved: the sensor is an IKEA TRADFRI motion sensor paired via the existing zigbee2mqtt bridge on the NUC; the friendly name `kitchen_motion_sensor` produces `binary_sensor.kitchen_motion_sensor_occupancy` and `sensor.kitchen_motion_sensor_battery` via MQTT autodiscovery. Both the spec and automations reference those entity IDs directly.
2. **Should motion also interact with Now-Playing?** Today Now-Playing is Sonos-driven; motion doesn't activate or deactivate it. Keep it that way — adding "motion pauses linger extension" would be over-design.
3. **Ghost wakes from the IMU.** The IMU INT (tap) wake is unchanged by this proposal, but worth noting: if motion + tap both arrive in quick succession (fridge closes → person standing at fridge double-taps), the motion-wake pulse and the IMU wake may race. The device handles this naturally: IMU wake proceeds as a gesture, motion-wake is idempotent (reads retained active_mode and acts). No extra code.
