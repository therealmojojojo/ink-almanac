## Context

The firmware is the last thing built, the first thing used. It is also, by design, the smallest capability in the project — MagInkDash and HomePlate ship firmwares of ~200 and ~500 lines of C++ respectively, and that's the target. Everything clever lives server-side; the device's job is to be stupid, reliable, and power-efficient.

This change also includes the wake-protocol as a separate capability because it is the bidirectional contract between firmware and HA — the only capability in the project with a symmetric dependency. Splitting it out makes the contract auditable from both sides.

## Goals / Non-Goals

**Goals:**
- Tiny firmware — pure thin client, no on-device logic beyond wake/fetch/display/sleep.
- Reliable tap detection via the LSM6DSO's hardware event registers.
- Power budget ≥ 6 weeks between charges under normal use.
- OTA updates so firmware iteration doesn't require USB after deploy.
- Graceful degradation when server-side is unreachable.

**Non-Goals:**
- Any on-device layout or rendering beyond drawImage of a pre-rendered PNG.
- Reducing HA's role. The device asks HA what to draw; HA owns the schedule.
- Proprietary protocols. MQTT is standard; everything else is HTTP.
- Supporting multiple Inkplate variants or other e-paper hardware. Inkplate 10 only.
- ESPHome. PlatformIO + Soldered library, as the tooling survey recommended.

## Decisions

### Sonos fast-path as a 3-minute background polling timer

The Now-Playing face promises activation within ~10 seconds of playback starting. The device sleeps for up to 60 minutes in Gallery mode. Without a push channel, there is no way to reconcile these two facts.

Three options were considered:

- **(a) 3-minute background polling timer** during Sonos-eligible hours (default 07:00–20:00, configurable). On each fast-path wake, the device reads retained MQTT `active_mode`; if unchanged, it returns to sleep immediately. If Now-Playing became active, it fetches and draws. Bounds activation latency to ~3 minutes during the eligible window. Costs ~20 extra wakes per hour during eligible hours (13 hours by default), each under 1 second.
- **(b) Companion always-listening ESP8266** translates MQTT pushes into a GPIO wake pulse on the Inkplate. Sub-second activation latency. Requires an extra board, extra wiring, extra firmware. Significant hardware and software scope increase.
- **(c) Accept the natural-wake latency** of up to 60 minutes in Gallery mode. Honest but weakens the Now-Playing feature to the point where it may not be worth building.

The ratified choice is **(a)**. The 3-minute worst case is acceptable for a kitchen dashboard, the power cost is bounded (fast-path wakes are tiny), and no additional hardware is needed. The strategy is documented as a table in the Sleep strategy requirement for auditability.

Latency softening: the sleep strategy spec states "~10 seconds" for the Now-Playing scenarios, but the fast-path upper bound is ~3 minutes. These are not contradictory — the 10-second number applies when the device is already awake or just completed a wake (common during active kitchen hours); the 3-minute bound applies when the device happens to be mid-sleep at activation time. Operator can tune the fast-path cadence (2 min? 5 min?) via config after living with it.

### PIR disabled during quiet hours

Rationale: during 00:00–05:00, movement in the kitchen is almost always someone briefly passing through (late-night glass of water, bathroom visit) — waking the display is unhelpful and wastes battery. Night mode has its own slow cadence for minute visibility. IMU INT stays armed because a deliberate double-tap at 03:00 should still toggle.

### MQTT retained messages for state coordination

The fundamental problem: ESP32 in deep sleep can't hold a network connection. HA can't "push" to a sleeping device. We compensate by making HA's state readable via MQTT retained messages — the device wakes (on its own schedule or external triggers) and reads current state. Functional push is replaced by guaranteed-available-on-wake state.

Alternative considered: polling HA's REST API. Rejected because REST requires HA to be up and reachable at every wake; retained MQTT messages are available even if HA briefly restarts (the broker persists them).

Alternative considered: companion-device GPIO wake. Rejected as hardware-scope creep.

### Active-mode decided by HA, not device

The device doesn't know about the schedule. It asks HA. Rationale: avoids duplicating schedule logic across HA and firmware. If the schedule changes (e.g., night starts at 22:30), only HA config updates; firmware never needs reflashing.

Fallback: if HA is unreachable, the device infers mode from local time via the default schedule (hardcoded in firmware as a last resort). The default schedule SHALL match whatever is currently in HA; documented clearly.

### Hardware tap detection via LSM6DSO INT pin

The LSM6DSO has configurable tap-detect registers that raise INT1 when a tap event occurs in hardware — no continuous polling, no CPU wake for every micro-acceleration. Rationale: essential for power budget. Polling-based tap detection would keep the CPU awake far too much.

Double-tap uses the IMU's built-in double-tap window (configurable, default ~200ms).

### No gyroscope door filter

An earlier revision of this design proposed a gyroscope-based filter to suppress tap-looking impulses caused by fridge-door rotation. The device is now wall-mounted, so there is no door rotation to filter. The gyro-burst read, the rotation-history RTC slot, and the suppression window were removed along with the door-filter test corpus.

### Partial refresh with ghost-clear cadence

Partial refresh is cheap but introduces ghosting. Every 30 partial refreshes, force a full refresh. Rationale: balances battery (partial is cheaper) with readability (ghosting accumulates).

Partial refresh applies only within a mode (minute region update); mode changes are always full-refresh.

### Error-state indicator, not blanking

Failures hide the old content with a tiny corner indicator rather than blanking the display. Rationale: a stale face beats no face on a wall-mounted display. The operator learns "that little dot means the server is down," no dashboards die.

### OTA from the start

Flashing via USB requires the frame off the fridge. OTA from day one means firmware iteration is a command line away. Rationale: reduces friction on what will be a long tail of tweaks (tap threshold, ghost-clear cadence, power tuning).

### Secrets in an include file, not config server

Simpler than centralized secret management. Rationale: one device, one installation.

### Inkplate 10 only, for now

The Inkplate library supports multiple variants via compile-time selection. This firmware hardcodes Inkplate 10. Rationale: the project is the Inkplate 10; polymorphism adds no value and obscures the code.

## Risks / Trade-offs

- **MQTT broker dependency.** If the broker dies, the device falls back to time-of-day inference and the renderer-unreachable indicator appears. Acceptable; the broker is part of HAOS and very stable.

- **Polling-wake cost.** If timer-based wake fires every 15 minutes for Summary/Weather, the daily wake count is ~96. Each wake is ~5-10 seconds. That's 8–16 minutes of active time per 24 hours — within budget, but tight during active hours. Mitigation: time-gated wake (e.g., 15-min only during 06:30–23:00, 60-min overnight).

- **Tap false positives.** Without the door filter, wall bumps and cabinet slams can register as taps. Mitigation: the tap is benign (a single Weather peek auto-reverts in 5 minutes), and `kTapThreshold` is tunable if false positives prove bothersome in situ.

- **OTA bricking.** A bad OTA can brick the device. Mitigation: the ESP32's OTA partition system allows rollback on failed boot; Soldered library supports this pattern. Document carefully.

- **Power budget math may be optimistic.** Until we have the hardware, the estimates are back-of-envelope. Mitigation: the spec requires the document, but the 6-week target is aspirational; reality may be 4-5 weeks. Acceptable given kitchen reach-ability.

- **Inkplate 10 v1.3 IO expander bugs.** Some Inkplate 10 v1.3 units have documented issues with the MCP23017 IO expander. Mitigation: use the Soldered library's v8+ which addresses the worst ones; test early.

## Migration Plan

This change depends on hardware arrival. Ratification and implementation proceed before hardware, but flashing and field validation require the device.

1. Ratify specs.
2. Implement `firmware/` with stubs that can compile without the Inkplate hardware present (using Arduino-compatible test builds where possible).
3. When hardware arrives: flash via USB, run through each spec scenario, document results.
4. Iterate on the power budget and gesture thresholds based on real-world measurement.
5. Move to OTA for all subsequent updates.

Rollback: revert firmware via OTA to the prior build. In extremis, re-flash via USB. Delete `firmware/` if abandoning the project.

## Open Questions

1. **Exact LSM6DSO registers for tap thresholds.** Needs tuning against the actual glass thickness and mounting rigidity. Empirical during hardware validation.

2. **PIR false-positive rate in a kitchen.** Kitchens have lots of motion (pets, cooking steam, fans). The 5-minute cooldown limits the damage, but a too-sensitive PIR wastes battery. Empirical.

3. **OTA mechanism.** ArduinoOTA is simple; ESP32 HTTP OTA is more flexible. Defer to implementation.

4. **Whether to do minute-tick in Summary.** The spec allows it but cautions on ghost-cadence. We may decide to skip the minute tick in Summary and only update it on the 15-min timer. Defer to field testing.

5. **Config update path.** If we change WiFi credentials, we need USB access. Consider a captive-portal fallback for first-time provisioning. Out of scope initially; revisit if needed.
