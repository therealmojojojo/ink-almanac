# Tasks — Pushable wake schedule

## 1. Firmware — types and storage

- [x] 1.1 `firmware/include/wake.h`: add `TierEntry` (8 B) and `Schedule` (40 B) structs with size static_asserts; add `parseSchedule(json)`, `resolveSchedule()`, `resolveScheduleColdBoot()`, `kDefaultSchedule` declarations.
- [x] 1.2 `firmware/src/wake.cpp`: add `RTC_DATA_ATTR volatile Schedule g_schedule_cache` next to existing `g_persisted`.
- [x] 1.3 `firmware/src/wake.cpp`: implement `kDefaultSchedule` matching today's `tierFor()` (Night 22:00 full=15; Morning 06:30 full=15 poll=3 partial=1; Midday 10:00 full=30 partial=5; Evening 17:00 full=15 poll=3 partial=1). `partial_brings_poll` is derived, not stored.

## 2. Firmware — JSON parser

- [x] 2.1 `firmware/src/wake.cpp`: implement `parseSchedule(json)` — bounds checks, divisibility checks, tier-count check, name-set check, monotonic-starts check, `start_min % full_min == 0` alignment check; return `Schedule{}` on any failure with FW_LOG of the violation.
- [x] 2.2 Implement helpers: whitespace-tolerant key search, tier-substring scoping (so `pickInt` calls operate within a single tier's `{...}`), integer parser with overflow protection (reject < INT16_MIN, > INT16_MAX), and `fnv32(const std::string&)` for payload-hash dedup.
- [x] 2.3 Empty-payload short-circuit in the caller (Phase 4 wiring): `if (payload.empty()) return;` before any hashing or parsing.

## 3. Firmware — NVS layer

- [x] 3.1 `firmware/src/wake.cpp` (ARDUINO-only): wrap `nvs_open("inkplate", READWRITE)`, `nvs_get_blob("sched_v1")`, `nvs_set_blob("sched_v1", ...)`, `nvs_commit()` calls. Host build: stub functions that read/write a static.
- [x] 3.2 NVS read SHALL verify exact `sizeof(Schedule)` bytes returned AND `version == 1` byte; reject mismatches and fall through to the next layer.
- [x] 3.3 `resolveSchedule()` / `resolveScheduleColdBoot()`: implement RTC → NVS → baked-default fallback chain.
- [x] 3.4 `applySchedule(parsed)`: write order is **NVS first, commit, RTC last**. NVS failure logs but does not abort RTC update. RTC update is unconditional once parse+validate succeeded.

## 4. Firmware — wire planWake

- [x] 4.1 `firmware/include/wake.h`: change `planWake` signature to take a `const Schedule&` parameter.
- [x] 4.2 `firmware/src/wake.cpp`: replace `tierFor()` with linear scan over `schedule.tiers[4]`, handling the wrap-at-midnight tier. `pathForMinute` derives `partial_brings_poll` at the use site (`partial_min > 0 && poll_min == 0`). Algorithm otherwise identical.
- [x] 4.3 `firmware/src/main_loop.cpp`: pass the resolved schedule from `tick()` into `planWake()`.

## 5. Firmware — MQTT read + parse on Full / Poll

- [x] 5.1 `firmware/src/main_loop.cpp` `doFull` and Poll/PollPartial paths: after `mqttConnect` success, fetch `inkplate/command/schedule` retained payload via `transport.mqttReadRetained`.
- [x] 5.2 Hash + dedup: skip parse if hash matches `g_schedule_cache.payload_hash`.
- [x] 5.3 On hash mismatch: parse, validate, on success → `applySchedule`. On failure → keep current cache, log diag flag.

## 6. Firmware — diag + state/device JSON

- [x] 6.1 `firmware/include/diag.h`: extend `Entry::flags` doc — bit5 = schedule_loaded_from_cache, bit6 = schedule_loaded_from_nvs, bit7 reserved.
- [x] 6.2 `firmware/src/main_loop.cpp`: set bit5 / bit6 when populating diag entries based on `resolveSchedule` outcome.
- [x] 6.3 `firmware/include/battery.h` + `firmware/src/battery.cpp`: add `const char* schedule_hash` arg to `toDeviceStateJson`; emit `"schedule_hash":"<8-hex>"` in JSON. When `g_schedule_cache.valid == 0`, pass `"00000000"`.
- [x] 6.4 `firmware/src/main_loop.cpp` `doFull`: format `g_schedule_cache.payload_hash` as 8-hex, pass to `toDeviceStateJson`.

## 7. Host tests

- [x] 7.1 New `firmware/test/scenarios/wake_schedule_parse_tests.cpp` covering: happy path (compact JSON); happy path (pretty-printed, multi-line, indented); whitespace variants around colons; missing version; wrong version; non-integer fields; full_min=0; full_min>720; poll_min>=full_min; partial_min>full_min; non-divisible cadences; misaligned `start_min` vs `full_min`; integer overflow (e.g., `full_min: 99999999`); negative integers; only 3 tiers; 5 tiers; unknown tier name; duplicate tier name; non-monotone starts; empty payload (must short-circuit, not error); bad UTF-8 in name fields; trailing garbage in JSON; tier objects in different order than canonical.
- [x] 7.2 New `firmware/test/scenarios/wake_schedule_plan_tests.cpp` — for the default schedule, assert `planWake` returns identical Path/minutes_to_next_wake as the existing `schedule_tests.cpp` cases. Plus 2-3 alternative schedules with different cadences.
- [x] 7.3 New `firmware/test/scenarios/wake_schedule_persistence_tests.cpp` — RTC empty + NVS valid → resolve from NVS; both empty → baked default; RTC valid → use RTC (no NVS read).
- [x] 7.4 Update `firmware/test/scenarios/main_loop_tests.cpp` if it asserts on planWake's old signature.

## 8. HA

- [x] 8.1 New file `ha/config/wake_schedule.yaml` — operator-editable, populated with the current baked-default values (no `partial_brings_poll`).
- [x] 8.2 New file `ha/automations/publish_wake_schedule.yaml` — on `homeassistant.start` and on file-change trigger, read the YAML and validate it with the **same rules the firmware enforces** (so a typo fails loud at deploy time, not silently at the next Full):
    - `version == 1`.
    - Exactly 4 tiers; names are the canonical set `{night, morning, midday, evening}`, each present exactly once.
    - Each `start` parses as `HH:MM` with hour in `0..23`, minute in `0..59`; the four resulting `start_min` values are pairwise distinct.
    - Per tier: `1 ≤ full_min ≤ 720`, `0 ≤ poll_min < full_min`, `0 ≤ partial_min ≤ full_min`. Non-integer or negative values reject.
    - Per tier: if `poll_min > 0`, require `full_min % poll_min == 0`; if `partial_min > 0`, require `full_min % partial_min == 0`.
    - Per tier: `start_min % full_min == 0` (start must align to the Full cadence).
  On any validation failure: emit a `persistent_notification` (so the operator sees it without scraping logs) AND log `error`, AND do NOT publish (the broker keeps the previous retained value, the device keeps running on its current schedule). On success: render the validated YAML to the canonical JSON shape and publish retained to `inkplate/command/schedule`.
- [x] 8.3 `ha/integrations/mqtt.yaml`: add `sensor.inkplate_device_schedule_hash` reading the `schedule_hash` field of `inkplate/state/device`. State value is the truncated hash; full hash exposed as `hash_full` attribute. Lets the operator confirm the device picked up a published schedule.
- [x] 8.4 `ha/integrations/mqtt.yaml`: expose the *expected* hash (computed HA-side from the published JSON payload) as a template sensor `sensor.inkplate_schedule_hash_expected`. This is the only practical way for the operator to confirm "the device has adopted my latest edit" without manually FNV-32-hashing the payload by hand; pair it with `sensor.inkplate_device_schedule_hash` from 8.3 in the same dashboard card. Implementation: an `mqtt` sensor subscribed to `inkplate/command/schedule` whose `value_template` runs FNV-32 over the raw payload (Jinja `|` filter or a small `pyscript`/template macro).

> **Pre-existing infrastructure to preserve when implementing 8.3/8.4** —
> `ha/integrations/mqtt.yaml` already carries:
>
>   - `sensor.inkplate_device_diag` — the per-wake diag ring (added in
>     commit `3bc6a98` and extended in `03c4471`). Reads
>     `value_json.diag` from `inkplate/state/device`.
>   - `sensor.inkplate_device_wifi_rssi` — the device's WiFi link
>     quality in dBm, reported on every Full publish (added in commit
>     `7ad23ee`, status: **implemented**, `kBuildVersion`
>     `0.4.1-wifi-rssi`). Reads `value_json.wifi_rssi`.
>   - `binary_sensor.inkplate_device_epd_power_good` — TPS65186 PMIC
>     fault indicator (added under `add-epd-power-good-diagnostic`).
>
> When this change adds the schedule-hash sensor (and optionally the
> template-sensor for HA-side comparison), it MUST extend the existing
> `sensor:`/`binary_sensor:` blocks rather than replace them. The
> review checklist for the schedule change's HA-side deploy:
> `ha deploy && verify all four mqtt-derived sensors above are still
> populated alongside the new schedule_hash sensor`.

## 9. Spec deltas

- [x] 9.1 `openspec/changes/add-pushable-wake-schedule/specs/device-firmware/spec.md` — ADDED requirement: dynamic-schedule resolution + parse + RTC/NVS caching.
- [x] 9.2 `openspec/changes/add-pushable-wake-schedule/specs/device-wake-protocol/spec.md` — ADDED requirement: `inkplate/command/schedule` retained topic, JSON shape, validation contract.
- [x] 9.3 `openspec/changes/add-pushable-wake-schedule/specs/ha-integrations/spec.md` — ADDED requirement: HA publishes the schedule to MQTT on start + on file change.

## 10. Validation

- [x] 10.1 `openspec validate add-pushable-wake-schedule` exits 0.
- [x] 10.2 Host build green, doctest 0 failed.
- [x] 10.3 PlatformIO inkplate10 build green.
- [x] 10.4 Smoke test on device: flashed `0.5.0-pushable-schedule`, deployed HA, observed (a) cold-boot publish with `schedule_hash=00000000` (baked default), (b) hash converge to `f676e451` after first Full reads retained MQTT, (c) hash converge to `dfea04d5` after editing midday `partial_min` 5→10 and redeploying, (d) hash converge to `fa9ba758` after editing evening `full_min` 15→1, with diag entry `tFG2f` confirming bit5 (`schedule_loaded_from_cache`) set on the next warm wake.
