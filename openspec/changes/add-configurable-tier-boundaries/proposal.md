# Extract schedule tier boundaries to runtime config

> **Status — 2026-04-27**: proposed; not started.

## Why

Tier boundaries (Morning starts 06:30, Midday 10:00, Evening 17:00, Night 22:00) are currently duplicated in two places that must stay in sync:

- `firmware/src/wake.cpp:tierFor()` — as `constexpr` minute-of-day integers (`390 / 600 / 1020 / 1320`)
- `ha/automations/schedule.yaml` and `ha/automations/gesture_override.yaml` — as Jinja literal hours (`6*60+30`, `10*60`, etc.)

Changing the schedule today means hand-editing both, recompiling firmware, redeploying HA, and remembering not to skip either side. The two sides have already drifted once during this codebase's history (caught by tests). The natural cadence of changes — DST shifts, lifestyle changes, "Gallery should start at 11 instead of 10" — is high enough that this duplication will keep biting.

The companion problem: the operator has no way to adjust the schedule without a build. Quiet hours, Sonos windows, and the alternation offset already live in HA helpers (`input_datetime`, `input_number`) and propagate to the firmware via the retained `inkplate/command/sleep_strategy` topic. Tier boundaries should follow the same pattern.

## What Changes

- **HA helpers**: add four `input_datetime` helpers in `ha/integrations/helpers.yaml`:
  - `inkplate_morning_start` (default `06:30`)
  - `inkplate_midday_start` (default `10:00`)
  - `inkplate_evening_start` (default `17:00`)
  - `inkplate_night_start` (default `22:00`)
- **HA publisher**: extend `ha/automations/sleep_strategy.yaml` (or add `tier_boundaries.yaml` mirroring the same pattern) to publish a retained payload to `inkplate/command/tier_boundaries` whenever any of the four helpers changes, plus on HA start (defensive against broker restarts).
- **HA Jinja**: rewrite `schedule.yaml` and `gesture_override.yaml` to source tier boundaries from the helpers instead of literals.
- **Firmware contract**: device reads `inkplate/command/tier_boundaries` on every wake (same pattern as `sleep_strategy`), caches `{morning_min, midday_min, evening_min, night_min}` in `Persisted` RTC RAM. `wake.cpp::tierFor()` consults the cached values; falls back to compile-time defaults if the cache is empty (cold boot before first MQTT read).
- **Per-tier cadence constants** (`{full=15, poll=3, partial=1}` etc.) stay `constexpr` in `wake.cpp`. They are tightly coupled to hardware behavior (panel refresh time, partial-pulse cost, post-Full cleanup timing) and don't change with operator preference.
- **Validation**: HA-side helper validator rejects boundary configurations that aren't strictly increasing (Morning < Midday < Evening < Night) or that leave a tier shorter than 30 minutes. Firmware-side: malformed payload → log and fall back to compile-time defaults.
- **Documentation**: update `firmware/docs/wake-protocol.md § Refresh schedule` and `firmware/docs/config.md § Schedule planner constants` to mark tier boundaries as runtime-configurable; cross-link the new HA helpers.

## Capabilities

### Modified Capabilities

- **`device-wake-protocol`**: new retained MQTT topic `inkplate/command/tier_boundaries`; new fallback semantics for malformed / absent payload.
- **`ha-integrations`**: four new `input_datetime` helpers; new (or extended) publisher automation; tier-boundary references in `schedule.yaml` and `gesture_override.yaml` switch from literals to helper reads.

### New Capabilities

None. This is a refactor that moves an existing concept from compile-time to runtime config.

## Impact

- **Eliminates a known source of drift** between firmware and HA. Single source of truth (the helpers) on the operator's edit surface.
- **Operator-tunable schedule** without recompiling. DST adjustments, lifestyle shifts, A/B tests on Gallery vs Weather hours are now UI changes.
- **Backward-compatible**: the firmware's `tierFor()` keeps the same constants as defaults, so a device that never receives the new MQTT topic behaves identically to today.
- **Bound on operator harm**: HA-side validation rejects malformed configs before publish; firmware-side validation rejects malformed payloads on read. Wrong-but-valid configurations (e.g., Morning starting at 03:00) are the operator's choice and not the schema's job to prevent.
- **Testing surface**: existing `firmware/test/scenarios/schedule_tests.cpp` continues to assert default behavior (cache empty → fallback). New scenarios cover (a) cached-boundary path producing a different tier classification than defaults, (b) malformed payload falls back, (c) HA-side helper validator rejects non-monotone boundaries.
- **Out of scope**: per-tier cadence constants, alternation period (15/30/15 min), tier→main-face mapping. These remain compile-time / YAML-time and would be separate proposals if ever needed.
