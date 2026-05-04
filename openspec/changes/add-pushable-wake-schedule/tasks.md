# Tasks — Pushable wake schedule

## 1. Firmware — types and storage

- [ ] 1.1 `firmware/include/wake.h`: add `TierEntry` (8 B) and `Schedule` (40 B) structs with size static_asserts; add `parseSchedule(json)`, `resolveSchedule()`, `resolveScheduleColdBoot()`, `kDefaultSchedule` declarations.
- [ ] 1.2 `firmware/src/wake.cpp`: add `RTC_DATA_ATTR volatile Schedule g_schedule_cache` next to existing `g_persisted`.
- [ ] 1.3 `firmware/src/wake.cpp`: implement `kDefaultSchedule` matching today's `tierFor()` (Night 22:00 full=15; Morning 06:30 full=15 poll=3 partial=1; Midday 10:00 full=30 partial=5; Evening 17:00 full=15 poll=3 partial=1). `partial_brings_poll` is derived, not stored.

## 2. Firmware — JSON parser

- [ ] 2.1 `firmware/src/wake.cpp`: implement `parseSchedule(json)` — bounds checks, divisibility checks, tier-count check, name-set check, monotonic-starts check, `start_min % full_min == 0` alignment check; return `Schedule{}` on any failure with FW_LOG of the violation.
- [ ] 2.2 Implement helpers: whitespace-tolerant key search, tier-substring scoping (so `pickInt` calls operate within a single tier's `{...}`), integer parser with overflow protection (reject < INT16_MIN, > INT16_MAX), and `fnv32(const std::string&)` for payload-hash dedup.
- [ ] 2.3 Empty-payload short-circuit in the caller (Phase 4 wiring): `if (payload.empty()) return;` before any hashing or parsing.

## 3. Firmware — NVS layer

- [ ] 3.1 `firmware/src/wake.cpp` (ARDUINO-only): wrap `nvs_open("inkplate", READWRITE)`, `nvs_get_blob("sched_v1")`, `nvs_set_blob("sched_v1", ...)`, `nvs_commit()` calls. Host build: stub functions that read/write a static.
- [ ] 3.2 NVS read SHALL verify exact `sizeof(Schedule)` bytes returned AND `version == 1` byte; reject mismatches and fall through to the next layer.
- [ ] 3.3 `resolveSchedule()` / `resolveScheduleColdBoot()`: implement RTC → NVS → baked-default fallback chain.
- [ ] 3.4 `applySchedule(parsed)`: write order is **NVS first, commit, RTC last**. NVS failure logs but does not abort RTC update. RTC update is unconditional once parse+validate succeeded.

## 4. Firmware — wire planWake

- [ ] 4.1 `firmware/include/wake.h`: change `planWake` signature to take a `const Schedule&` parameter.
- [ ] 4.2 `firmware/src/wake.cpp`: replace `tierFor()` with linear scan over `schedule.tiers[4]`, handling the wrap-at-midnight tier. `pathForMinute` derives `partial_brings_poll` at the use site (`partial_min > 0 && poll_min == 0`). Algorithm otherwise identical.
- [ ] 4.3 `firmware/src/main_loop.cpp`: pass the resolved schedule from `tick()` into `planWake()`.

## 5. Firmware — MQTT read + parse on Full / Poll

- [ ] 5.1 `firmware/src/main_loop.cpp` `doFull` and Poll/PollPartial paths: after `mqttConnect` success, fetch `inkplate/command/schedule` retained payload via `transport.mqttReadRetained`.
- [ ] 5.2 Hash + dedup: skip parse if hash matches `g_schedule_cache.payload_hash`.
- [ ] 5.3 On hash mismatch: parse, validate, on success → `applySchedule`. On failure → keep current cache, log diag flag.

## 6. Firmware — diag + state/device JSON

- [ ] 6.1 `firmware/include/diag.h`: extend `Entry::flags` doc — bit5 = schedule_loaded_from_cache, bit6 = schedule_loaded_from_nvs, bit7 reserved.
- [ ] 6.2 `firmware/src/main_loop.cpp`: set bit5 / bit6 when populating diag entries based on `resolveSchedule` outcome.
- [ ] 6.3 `firmware/include/battery.h` + `firmware/src/battery.cpp`: add `const char* schedule_hash` arg to `toDeviceStateJson`; emit `"schedule_hash":"<8-hex>"` in JSON. When `g_schedule_cache.valid == 0`, pass `"00000000"`.
- [ ] 6.4 `firmware/src/main_loop.cpp` `doFull`: format `g_schedule_cache.payload_hash` as 8-hex, pass to `toDeviceStateJson`.

## 7. Host tests

- [ ] 7.1 New `firmware/test/scenarios/wake_schedule_parse_tests.cpp` covering: happy path (compact JSON); happy path (pretty-printed, multi-line, indented); whitespace variants around colons; missing version; wrong version; non-integer fields; full_min=0; full_min>720; poll_min>=full_min; partial_min>full_min; non-divisible cadences; misaligned `start_min` vs `full_min`; integer overflow (e.g., `full_min: 99999999`); negative integers; only 3 tiers; 5 tiers; unknown tier name; duplicate tier name; non-monotone starts; empty payload (must short-circuit, not error); bad UTF-8 in name fields; trailing garbage in JSON; tier objects in different order than canonical.
- [ ] 7.2 New `firmware/test/scenarios/wake_schedule_plan_tests.cpp` — for the default schedule, assert `planWake` returns identical Path/minutes_to_next_wake as the existing `schedule_tests.cpp` cases. Plus 2-3 alternative schedules with different cadences.
- [ ] 7.3 New `firmware/test/scenarios/wake_schedule_persistence_tests.cpp` — RTC empty + NVS valid → resolve from NVS; both empty → baked default; RTC valid → use RTC (no NVS read).
- [ ] 7.4 Update `firmware/test/scenarios/main_loop_tests.cpp` if it asserts on planWake's old signature.

## 8. HA

- [ ] 8.1 New file `ha/config/wake_schedule.yaml` — operator-editable, populated with the current baked-default values (no `partial_brings_poll`).
- [ ] 8.2 New file `ha/automations/publish_wake_schedule.yaml` — on `homeassistant.start` and on file-change trigger, read the YAML, perform structural validation (version present, 4 tiers, canonical names, parseable `start` strings), render to the canonical JSON shape, publish to `inkplate/command/schedule` retained. On structural failure: log `warning`, do not publish.
- [ ] 8.3 `ha/integrations/mqtt.yaml`: add `sensor.inkplate_device_schedule_hash` reading the `schedule_hash` field of `inkplate/state/device`. State value is the truncated hash; full hash exposed as `hash_full` attribute. Lets the operator confirm the device picked up a published schedule.
- [ ] 8.4 `ha/integrations/mqtt.yaml` (optional): also expose the published schedule's expected hash as a `template` sensor, so the operator can directly compare device-side vs HA-side without arithmetic.

## 9. Spec deltas

- [x] 9.1 `openspec/changes/add-pushable-wake-schedule/specs/device-firmware/spec.md` — ADDED requirement: dynamic-schedule resolution + parse + RTC/NVS caching.
- [x] 9.2 `openspec/changes/add-pushable-wake-schedule/specs/device-wake-protocol/spec.md` — ADDED requirement: `inkplate/command/schedule` retained topic, JSON shape, validation contract.
- [x] 9.3 `openspec/changes/add-pushable-wake-schedule/specs/ha-integrations/spec.md` — ADDED requirement: HA publishes the schedule to MQTT on start + on file change.

## 10. Validation

- [ ] 10.1 `openspec validate add-pushable-wake-schedule` exits 0.
- [ ] 10.2 Host build green, doctest 0 failed.
- [ ] 10.3 PlatformIO inkplate10 build green.
- [ ] 10.4 Smoke test on device: flash, watch diag ring report `bit6` (NVS hit) on first cold boot post-flash; modify YAML, redeploy; observe diag ring report `schedule_updated_this_wake` flag on next Full.
