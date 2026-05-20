# Tasks — Night text-clock partials + pool-only poetic line

> **Status — 2026-05-20**: 5/41 complete — foundation shipped today (bake tool + renderer clock-zone + Persisted scaffolding). Generated `firmware/src/generated/night_phrases.{h,cpp}` exist; both host sim and ESP32 builds green; smoke contact-sheet rendering verified. Flash is **still at 81.9%** because the linker drops the new ~150 KB of phrase data as dead code until §5 (firmware dispatch) calls `phraseForMinute()` — the proposal's ≈93% projection will only materialize then.
>
> Two implementation choices worth recording:
> - **§4.2 is skipped (no-op).** The clock-glyphs precedent doesn't use a separate `firmware/include/<name>.h` shim header; the bake tool's generated `firmware/src/generated/night_phrases.h` is the public API surface. Future callers `#include "generated/night_phrases.h"` directly. Marking 4.2 closed.
> - **Bake tool reuses `renderer/src/modes/night.ts::nightPhrase(h, m)`** as the single source of truth for the 25 phrases. Today that gives "twelve o'clock" / "quarter to twelve" / "half past twelve" at h=0; the proposal originally aspired to "midnight" variants instead. Lockstep with the renderer's PNG render wins out — if the operator ever wants "midnight" in the vocabulary, update `nightPhrase()` and the bake's output re-syncs automatically.

## 1. Renderer — bake-night-phrases tool

- [x] 1.1 New `renderer/src/tools/bake-night-phrases.ts`. Reads the Night face's CSS for the phrase element's font-family, font-size, font-weight, color. **Sources the 25 phrases by importing `renderer/src/modes/night.ts::nightPhrase(h, m)` and iterating over the partial-eligible minutes** (every 15 min in the Night tier, where `min_of_day % 15 == 0`, in the 22:00–06:30 window) — keeps the runtime PNG and baked bitmaps lockstep-consistent. For each phrase: render via Playwright headless Chromium, threshold to 1-bit, tight-bounding-box crop. Emit `firmware/src/generated/night_phrases.h` (struct decl + `phraseForMinute` decl) and `night_phrases.cpp` (constexpr bitmap arrays + switch-statement lookup).
- [x] 1.2 1-bit threshold: pixels with luminance > 128 → 0 (white), else 1 (black). MSB-first within each byte, row-major. Pad each row to a byte boundary; no inter-row padding (height implicit from `data length / row_bytes`). Verified: bake produces 25 entries, max bitmap 684×94 px, total 149.4 KB.
- [x] 1.3 Smoke check: `npm run bake:night-phrases -- --smoke` writes a 5×5 contact-sheet PNG to `/tmp/night_phrases_preview.png`. Visually verified on 2026-05-20; all 25 render cleanly with no clipping or font-fallback artefacts.
- [x] 1.4 Added `bake:night-phrases` script to `renderer/package.json` next to `bake:clock-glyphs`. (README documentation deferred to validation §13.)

## 2. Build wiring

- [ ] 2.1 PlatformIO `inkplate10` build: pre-build hook runs `npm run bake-night-phrases` in the renderer/ directory IF `firmware/src/generated/night_phrases.cpp` is missing OR older than the bake script OR older than the Night face CSS. Use a small `extra_scripts` Python step in `platformio.ini`.
- [ ] 2.2 CMake host build: parallel `add_custom_command` so `firmware_sim` includes the same generated file when running tests. (Tests don't actually exercise the bitmap content, but the build needs to compile.)
- [x] 2.3 Confirmed the **opposite** convention: `firmware/src/generated/clock_glyphs.{h,cpp}` ARE tracked (the proposal's expectation that they were gitignored was wrong). Tracking the generated `night_phrases.{h,cpp}` the same way so CI / contributors don't need Playwright + Chromium installed to compile the firmware. Re-run the bake only when the bake script, the renderer's Night CSS, or the `nightPhrase()` vocabulary changes — that workflow lands with §2.1's pre-build hook.

## 3. Renderer — Night clock-zone JSON

- [x] 3.1 `renderer/src/render.ts`'s clock-zone selector extended to include `.night-phrase`. The existing infrastructure populates `clockZoneByMode` on every Full render of `night.png`, so `GET /display/night/clock-zone.json` will now return the live rectangle (no hardcoding needed). Stale comment about "Night splits hh/mm into two elements" replaced.
- [ ] 3.2 Verify `GET /display/night/clock-zone.json` returns 200 with the expected schema (no longer 404).
- [ ] 3.3 Update `firmware/docs/wake-protocol.md`'s per-face partial table — Night row no longer says "n/a — tier has no Partial cadence and renderer returns 404"; instead "yes — phrase bitmap blitted via `night_phrases::phraseForMinute`".

## 4. Firmware — types and storage

- [x] 4.1 `firmware/include/wake.h::Persisted`: added `uint16_t last_drawn_phrase_min = 0xffff` next to `last_drawn_hh` / `last_drawn_mm`. Cold-boot value-initialised to 0xffff; preserved across deep sleep via the existing `RTC_DATA_ATTR volatile Persisted g_persisted{}` mechanism.
- [N/A] 4.2 No separate shim header. Following the `clock_glyphs` precedent, the bake tool's generated `firmware/src/generated/night_phrases.h` is the public API surface directly — `namespace fw::night_phrases { struct Bitmap; const Bitmap* phraseForMinute(int); }`. Future callers `#include "generated/night_phrases.h"`.

## 5. Firmware — partial dispatch for Night

- [x] 5.1 `doPartial` dispatches to a new `doPartialNight` when `current_mode == Night`. Cold state (post-Full, sentinel `last_drawn_phrase_min == 0xffff`): pulse zone solid black once to wipe the PNG's 3-bit phrase pixels, then blit the new bitmap. Warm state (consecutive partials): seed-blit the previously-drawn phrase at its centered position, then blit the new one. The library's `partialUpdate1Bit` diff handles old→white and new→black in a single waveform cycle. Updates `last_drawn_phrase_min` to current `min_of_day`. Returns false when phrase set doesn't include the minute (caller promotes to Full per existing pattern).
- [x] 5.2 `doFull` post-Full cleanup has a Night branch ahead of the existing digit-clock cleanup. At a partial-eligible Full minute (edge cases like IMU tap at :15), pulses zone black + blits phrase + updates `last_drawn_phrase_min`. At top-of-hour Fulls (the normal cadence, :00 not in the phrase set), no over-paint — sets `last_drawn_phrase_min = 0xffff` so the next partial's cold-state wipe knows to fire. Also resets `last_drawn_hh/mm = 0xff` defensively in case the prior mode left them set.
- [N/A] 5.3 No separate `blitBitmap1Bit` helper file. The existing `IDisplay::drawBitmap1Bit(x, y, data, w, h)` primitive matches the bake tool's bitmap layout exactly (1bpp, MSB-first, row-padded). Used directly via two inline helpers (`nightBlitY` for vertical centering, `nightBlit` for the call). MockDisplay records the blit into its `bitmap_blits_` vector; host tests assert on the vector size + delta.

**Sidecar — extends Persisted with `clock_zone_w` / `clock_zone_h`** (uint16_t each, default 0) so the Night blit can vertically-center inside the renderer's 220u flex container. `fetchAndStoreClockZone` now parses `w` and `h` from the JSON. Pre-existing modes ignore the new fields (digit-clock path derives its rect from the baked Preset).

## 6. Firmware — host tests

- [x] 6.1 `firmware/test/scenarios/night_partial_tests.cpp` shipped with 6 test cases (all pass; total host suite 104/104):
    - "phraseForMinute exposes exactly the 25 partial-eligible minutes" + spot-check non-partial minutes return null.
    - "baked phrase bitmaps have reasonable dimensions" — width/height/data ptr sanity.
    - "Night cold-boot Full at 22:00 leaves phrase-min sentinel for first partial" — post-cleanup no-op at top-of-hour; clock_zone_h=220 / clock_zone_w=900 confirmed parsed from JSON.
    - "Timer @ Night 22:15 → Partial blits phrase bitmap, no Full promotion" — exact partialUpdate count (2: wipe + draw), no MQTT publish, last_drawn_phrase_min advances to 1335.
    - "Consecutive Night partials seed DMemoryNew with previous phrase" — 22:00 cold → 22:15 → 22:30, asserts last_drawn_phrase_min == 1335 entering 22:30 and 1350 after; warm-state path produces 2 partialUpdates + 2 bitmap blits (no fillRect after cold state).
    - "Timer @ Night :07 under 120/0/15 → Skip — sanity" — off-cadence guard.
- [x] 6.2 `clock_render_tests.cpp` already pins assertions to specific font_size presets (corner/compact/summary) — never asserts Night digit composition. No edit needed; confirmed by re-reading.

**Sidecar — discovered a 2-hour off-by-one in main_loop_tests.cpp's `kApr14_0800`**: the comment claims `1744617600 + 2*3600 = 08:00 UTC`, but 1744617600 is itself 08:00 UTC, so the constant is actually 10:00 UTC. Existing tests don't notice (they only check cadence-modulo behavior). night_partial_tests defines its own `localTime` helper with a corrected base so absolute min-of-day assertions land on the intended wall-clock values.

## 7. HA — pool rename + content

- [x] 7.1 `git mv ha/config/night_fallback_lines.yaml ha/config/night_poetic_pool.yaml`. File header comment updated: no more "fallback" framing; describes the bucket-change trigger model and the strict ASCII rules.
- [x] 7.2 Existing 112 entries re-audited: voice is consistent, all ASCII (no Romanian diacritics in use), no entries exceed budget — see §7.3 verification.
- [x] 7.3 Verified: `python3 -c '<audit>'` against `night_poetic_pool.yaml` reports 112 total / 0 regex fails / 0 length > 40.
- [ ] 7.4 (Operator follow-up, not blocking) Buckets at 8 entries already give good rotation; thin buckets can grow toward 12-15 if multi-night repetition becomes visible.

## 8. HA — picker script

- [x] 8.1 `generate_poetic_weather_line.sh` rewritten as ~40 LOC pool-only picker. Reads bucket as the *last* positional arg so legacy 4-arg invocations (summary, temp_c, wind, bucket) still work during a partial deploy. All LLM machinery (API key loading, request body, response parsing, length-clamping, fallback-decision tree) deleted.
- [x] 8.2 Smoke-tested locally against the project-local pool — buckets `clear_cold`, `rain`, `windy_dry`, `drizzle` (previously dormant) all return valid lines; `bogus_bucket` and empty bucket arg fall through to `cloudy`. The script's regex/length filter is on the *line*, so broken pool entries are skipped at runtime.
- [x] 8.3 Performance: ~120 ms per pick (Python startup dominates; YAML load + shuffle + regex is ~5 ms). Above the < 100 ms target by 20 ms but acceptable — the script runs at most a few times per night.

## 9. HA — bucket sensor + automation rewrite

- [x] 9.1 New `ha/sensors/poetic_weather_bucket.yaml` defines `sensor.inkplate_night_poetic_bucket`. Lifts the bucket logic from the old automation and adds a `wind_kph >= 25` override that activates `windy_dry` for `cloudy` / `partly_cloudy` conditions (matches the operator's actual weather provider, which doesn't emit `windy` / `windy-variant` as condition values).
- [x] 9.2 Rewrote `ha/automations/poetic_weather.yaml`. Hourly `time_pattern` trigger replaced with `state_changed` on the bucket sensor (`not_to: [unknown, unavailable, ""]`). Kept `homeassistant.start` as a safety re-publish. Gated by `input_boolean.inkplate_publisher_enabled` + the night-hours template condition (21:00-07:00).
- [x] 9.3 Action passes the current bucket sensor value to `shell_command.generate_poetic_weather_line` via `bucket:` data field. Also updated the `shell_commands.yaml` entry to drop the 3 legacy positional args.
- [ ] 9.4 Smoke deferred to post-deploy: requires forcing a bucket transition via Developer Tools, will land in §13 validation.

## 10. HA — cleanup

- [x] 10.1 `git rm ha/config/poetic_weather_line.yaml`. Updated `ha/docs/secrets-checklist.md` and `ha/docs/troubleshooting.md` accordingly.
- [x] 10.2 Confirmed `generate_astro_event.py` still reads `anthropic_api_key` (lines 467, 473, 478, 531). Key retained in `ha/secrets.yaml`.

## 11. Spec deltas

- [x] 11.1 `device-firmware/spec.md` delta updated to reflect the cold-state wipe pulse, the 120/0/15 schedule, and the vertical centering math. `openspec validate` passes.
- [x] 11.2 `rendering-pipeline/spec.md` delta updated: live `clockZoneByMode` measurement (not hardcoded), sourcing the 25 phrases via `nightPhrase()` for lockstep with the renderer's PNG vocabulary, 150 KB empirical footprint, and the "files committed to git pending future pre-build hook" note.
- [x] 11.3 `ha-integrations/spec.md` delta updated: 112 actual entries (vs 65 minimum), `wind_kph >= 25` override path, last-positional-arg compatibility for the picker, time-of-day gate on the automation.

## 12. Supersede the old change

- [x] 12.1 Deleted `openspec/changes/replace-poetic-llm-with-pool/` (2026-05-05). Its scope is fully subsumed; commit message will note the supersession.

## 13. Validation

- [ ] 13.1 `openspec validate add-night-text-clock-partials` exits 0.
- [ ] 13.2 Host build green; doctest 0 failed (including new night_partial_tests).
- [ ] 13.3 PlatformIO inkplate10 build green. Verify flash usage stays under 95%. **Baseline (2026-05-19): 81.9%** (1,072,937 / 1,310,720 B); proposal estimates ≈ 93% post-bake. If the build exceeds 95%, revisit per-phrase bitmap compression (proposal §A risk 1) before shipping.
- [ ] 13.4 `ha/deploy.sh` succeeds.
- [ ] 13.5 Manually invoke `service: shell_command.generate_poetic_weather_line` with `bucket: clear_cold` from HA Developer Tools. Confirm `state/poetic_weather.txt` mtime updates and content is from the `clear_cold` bucket. Sensor `inkplate_poetic_weather_line` updates within `scan_interval` (300s).
- [ ] 13.6 Smoke test on device: flash, observe a 22:15 partial wake (or contrived equivalent at the next :15 boundary) → diag entry shows `tPN…` (Partial in Night mode) with bit4 set (partial_succeeded), no Full promotion. Visually confirm the phrase is rendered correctly.
- [ ] 13.7 Operator-eye check: the 1-bit firmware over-paint must visually match (or be acceptably close to) the 3-bit PNG's rendering of the same phrase at top-of-hour. If contrast / weight / kerning differ noticeably, tune the bake's threshold or font weight in step 1.1 and re-bake.
