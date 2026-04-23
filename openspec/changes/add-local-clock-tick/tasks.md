# Tasks — add-local-clock-tick

## 1. Firmware — local-clock render path

- [ ] 1.1 Add `Reason::LocalTick` to `firmware/include/wake.h`; extend `wake::toString()` and scenario switches.
- [ ] 1.2 Rework `firmware/src/main_loop.cpp::tick()` so the minute-tick early-return branch (currently lines 149–163) calls the new local-draw path instead of publishing-and-sleeping.
- [ ] 1.3 Add `firmware/src/clock_local.{cpp,h}` with `drawClockInto(framebuf, zone, epoch)` and `drawNightPhraseInto(framebuf, zone, epoch)`. Both render into a caller-provided rectangle using glyphs from the shipped font tables.
- [ ] 1.4 Add `firmware/src/night_phrases.{cpp,h}` implementing `nightPhrase(h, m) -> string` per the algorithm in `design.md`. Include a `word(h12)` helper.
- [ ] 1.5 Partial-refresh only the clock rectangle on a `LocalTick` wake; do NOT connect WiFi or MQTT.
- [ ] 1.6 Handle the ghost-clear cadence: when `partial_refresh_count` hits `kGhostClearPartialCount` on a `LocalTick` wake, promote to a full cycle instead (connect, fetch, full refresh).

## 2. Firmware — external RTC as primary clock

- [ ] 2.1 Add `firmware/src/hal/real/RealRTC.{cpp,h}` wrapping the Inkplate library's PCF85063A API (`rtcGetEpoch` / `rtcSetEpoch`).
- [ ] 2.2 Extend `hal::IClock` to expose the current epoch from the external RTC; fall back to `esp_timer_get_time()`-derived epoch when the external RTC is unreachable.
- [ ] 2.3 After a successful WiFi + NTP sync, write the new epoch back to the external RTC.
- [ ] 2.4 Document the CR2032 coin-cell as a required install step in `firmware/README.md` and in the physical-build checklist (`add-physical-build`).

## 3. Firmware — font assets

- [ ] 3.1 Add `renderer/scripts/gen-firmware-fonts.py` that reads a TTF and emits a `GFXfont` C header for a chosen subset.
- [ ] 3.2 Emit two headers: `firmware/include/assets/fonts/ClockDigits.h` (digits + `:`) and `firmware/include/assets/fonts/NightText.h` (lowercase letters + space + apostrophe).
- [ ] 3.3 Embed both as `const` data in firmware flash. Confirm total size <150 KB.
- [ ] 3.4 Wire `gen-firmware-fonts.py` into the firmware build (PlatformIO pre-build script or Makefile target) so font changes in the renderer propagate to firmware rebuilds.
- [ ] 3.5 Emit a glyph-table version hash into each generated header; firmware records and surfaces it in `state/device` for diagnostics.

## 4a. Firmware — tap as wake signal

- [x] 4a.1 Remove any firmware-side interpretation of tap kind as a semantic action (no hard-coded "single → Weather peek" or "double → Summary/Gallery toggle" logic). Firmware's only jobs on IMU wake are: identify kind, ack glyph, publish gesture, re-read active_mode. — main_loop.cpp was already free of that interpretation; the gesture publish was just in the wrong place (end of cycle, after active_mode was read). Reordered.
- [x] 4a.2 Add a post-publish MQTT grace window (default 2 s) during which the firmware subscribes to `inkplate/command/active_mode` and prefers any message received within the window over the pre-gesture retained value. — `ITransport::mqttWaitForMessage(topic, timeout_ms)` added; `RealTransport` shares a `waitImpl()` helper with `mqttReadRetained`; `MockTransport` returns the current retained snapshot (publish-hook makes HA responses synchronous in scenarios).
- [x] 4a.3 Expose `kGestureGraceMs` in `config.h` (default `2000`). Runtime override via HA helper deferred to the helpers-deploy step.
- [x] 4a.4 Simulator scenario: IMU wake publishes gesture; mock HA responds with updated active_mode within the window → device fetches the new face in the same cycle. (`main_loop_tests.cpp` "IMU wake: gesture published before active_mode resolved")
- [x] 4a.5 Simulator scenario: IMU wake; mock HA does NOT respond in the window → device fetches the pre-gesture face; ack glyph visible, no face change. (`main_loop_tests.cpp` "IMU wake: HA silent → keep pre-gesture face")
- [x] 4a.6 Simulator scenario: IMU wake during quiet hours; mock HA responds by NOT changing active_mode → device shows ack glyph, face stays as Night. (`main_loop_tests.cpp` "IMU wake during quiet hours: HA holds Night, no face change") Plus a bonus double-tap scenario confirming payload shape.

## 4. Firmware — status glyphs

- [ ] 4.1 Pre-render `ack` (stylized thumbs-up) and `error` (warning triangle) bitmaps at ~32×32u. Store as raw byte arrays in `firmware/include/assets/glyphs/`.
- [ ] 4.2 Add `firmware/src/status_glyph.{cpp,h}` with `showAck()` and `showError()` — each does a partial refresh into the top-right `status_slot` rectangle read from the cached zones.json (overlaying the battery indicator). No explicit `clearStatus()` needed: the next full refresh repaints the battery indicator and implicitly clears the glyph.
- [ ] 4.3 Call `showAck()` in `main_loop.cpp::tick()` when the wake reason is `IMU`, immediately after identifying the tap, before beginning the network round-trip.
- [ ] 4.4 Call `showError()` in the fetch-failure path. Do not call explicit clear — the next full-cycle refresh handles it.
- [ ] 4.5 Verify that full refreshes (schedule boundary / ghost-clear / mode change) restore the battery indicator and overwrite any lingering glyph pixels.

## 5. Firmware — zones bootstrap

- [ ] 5.1 On cold boot / OTA boot, before the first full fetch, attempt `GET /display/zones.json` and cache the body + version hash to LittleFS.
- [ ] 5.2 Keep a last-known-good copy; if the fetch fails, use the cached copy.
- [ ] 5.3 If no cache exists and the fetch fails, skip local-tick rendering entirely for this session; the full-cycle path still works.
- [ ] 5.4 Re-fetch zones.json on every cold boot (cheap) to pick up renderer-side layout changes without reflashing.
- [ ] 5.5 Persist the last-used zone map's version hash into RTC SRAM so mid-session wakes don't re-read flash.

## 6. Firmware — revised sleep strategy

- [ ] 6.1 Update `firmware/include/config.h` with the split cadence: `kLocalTickDaySec = 60`, `kLocalTickNightSec = 900`, per-mode `kFullFetchIntervalSec` values.
- [ ] 6.2 Update `firmware/src/wake.cpp::armMask()` to schedule `LocalTick` and full-fetch timers independently; both fire at their own cadence.
- [ ] 6.3 Update `firmware/docs/wake-protocol.md`: new wake reason, new cadence table.
- [ ] 6.4 Update `firmware/docs/config.md`: new config constants.
- [ ] 6.5 Update `firmware/docs/power-budget.md`: revised daily mAh math; assert against the 4000 mAh pack at 42 days with margin.

## 7. Renderer — zones endpoint

- [ ] 7.1 Export a canonical clock-zone table from `renderer/src/zones.ts` per face.
- [ ] 7.2 Add `GET /display/zones.json` to `renderer/src/server.ts` returning the table plus a sha256 version hash.
- [ ] 7.3 Serve the endpoint unauthenticated (it's public layout metadata, not secret).
- [ ] 7.4 Add test: zones.json version changes whenever the underlying table changes.

## 8. Renderer — Night approximate phrasing

- [ ] 8.1 Implement `nightPhrase(h, m)` and `wordForHour(h12)` in `renderer/src/modes/night.ts` using the exact algorithm from `design.md`.
- [ ] 8.2 Replace the precise `HH:MM` stacked clock on the Night face with the phrase text in Fraunces Italic display size.
- [ ] 8.3 Update snapshot goldens (`renderer/test/__golden__/night-*.png`) with the new layout.
- [ ] 8.4 Update `renderer/docs/faces.md` with the new Night face description.

## 9. Renderer — typography pin for firmware

- [ ] 9.1 Document which TTF file + weight + size the firmware bitmap-font codegen reads for the clock-digit set.
- [ ] 9.2 Document the same for the Night-phrase letter set.
- [ ] 9.3 CI check: renderer cannot change the pinned TTF without a corresponding firmware font-table version bump.

## 10. Simulator

- [ ] 10.1 Add `Reason::LocalTick` scenarios in `firmware/test/scenarios/`: wake fires, no network touched, framebuffer contains the expected clock glyphs, partial refresh called with the clock rectangle.
- [ ] 10.2 Add scenario: ghost-clear cadence promotes a `LocalTick` wake to a full cycle.
- [ ] 10.3 Add scenario: `IMU` wake emits the ack glyph before the network path; fetch failure emits the error glyph.
- [ ] 10.4 Add scenario: cold boot with zones.json reachable populates the cache; with it unreachable and no cache, local-tick is suppressed without crashing.
- [ ] 10.5 Add scenario: Night tick at 02:15 emits the phrase "quarter past two".
- [ ] 10.6 Update `power_budget.cpp` daily-cost expectations to the new ~115 mAh/day target and re-run the 42-day assertion.

## 11. Dashboard-faces spec alignment

- [ ] 11.1 Add a new requirement in `dashboard-faces` declaring `clock_zone` coordinates for Summary, Weather, Gallery (visual + text), and Night (Night's zone holds the phrase, not precise HH:MM).
- [ ] 11.2 Update the character-budget table: remove `weekday_label` + stacked-clock references for Night where precise time is implied; add `night_phrase` budget (≤24 chars, 1 line).
- [ ] 11.3 Night face layout requirement: phrase text in place of stacked clock; weekday label position unchanged.

## 12. HA architecture doc

- [ ] 12.1 Update `ha/docs/architecture.md` "Period-driven wake arming" table with the new cadence.
- [ ] 12.2 Update "The wake-latency ladder" section: tap latency improves (with wire) to ~1 s ack / ~8 s full; clock staleness is ≤ 1 min (day) / ≤ 15 min (night).
- [ ] 12.3 Note the PCF85063A + CR2032 as a hardware dependency for the clock-survives-power-events property.

## 13. Acceptance

- [ ] 13.1 On a fully-flashed device, verify minute-tick partial refresh completes in <1 s and uses no network (WiFi idle indicator).
- [ ] 13.2 Verify full-fetch cadence holds (renderer logs show one `/display/*.png` per 15-min / 60-min cycle per period).
- [ ] 13.3 Verify ack glyph appears within ~1.5 s of a tap (once INT1 wire is in place per `add-device-firmware §5.4`).
- [ ] 13.4 Verify error glyph appears when the renderer is unreachable; clears on next success.
- [ ] 13.5 Verify Night face at 02:15 displays "quarter past two"; at 03:45 displays "quarter to four".
- [ ] 13.6 Verify clock survives a LiPo swap (coin cell installed): after reconnecting, the first local-tick shows the correct time before NTP resync.
- [ ] 13.7 Power-budget simulator passes 42-day assertion with the new cadence.
