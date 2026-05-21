# device-firmware Specification — delta

## ADDED Requirements

### Requirement: Night-mode partial refresh via baked phrase bitmaps

When the active mode is Night and the schedule planner returns `Path::Partial` (or post-Full cleanup runs at a partial-eligible minute), the firmware SHALL render the time as a fuzzy-time English phrase ("quarter to three", "half past midnight", etc.) by blitting a baked 1-bit bitmap, NOT by composing digit glyphs.

The bitmap table SHALL be baked into firmware flash at build time by `renderer/src/tools/bake-night-phrases.ts`, which produces `firmware/src/generated/night_phrases.{h,cpp}`. The table SHALL contain exactly 25 entries — one per partial-eligible minute in the Night tier window (22:15, 22:30, 22:45, 23:15, …, 05:45, 06:15). The lookup function `fw::night_phrases::phraseForMinute(int min_of_day) → const Bitmap*` SHALL return non-null for the 25 bake-time minutes and `nullptr` for all others.

Bitmap format: 1-bit, MSB-first within each byte, row-major, padded to a byte boundary. Width and height are stored in the `Bitmap` struct.

`doPartial` Night branch:

- Look up the phrase bitmap for `local_min_of_day`. Null → return `false` (caller decides).
- **Cold state** (`Persisted::last_drawn_phrase_min == 0xffff` — the post-Full or post-cold-boot state where the 3-bit PNG text still occupies the phrase zone): pulse the zone solid black via `fillRect1Bit` + `partialUpdate1Bit` to overwrite the PNG's 3-bit AA pixels with a known 1-bit pattern, then blit the new phrase bitmap at its vertically-centered position + `partialUpdate1Bit`.
- **Warm state** (`last_drawn_phrase_min != 0xffff` — a previous partial drew a phrase): seed-then-draw — re-blit the previous-frame phrase to seed the library's `DMemoryNew`, then blit the new phrase, `partialUpdate1Bit`. Matches the existing seed-then-draw pattern used by digit-clock partials.
- Update `last_drawn_phrase_min` to the current minute.

`doFull` post-Full cleanup, Night branch: if and only if the Full happened to land on a partial-eligible minute (edge cases like an IMU tap forcing a Full at :15), pulse the phrase rectangle solid black + blit the phrase, mirroring the digit-clock cleanup pattern, and set `last_drawn_phrase_min` to the current minute. Top-of-hour Night Fulls (which are NOT in the 25-entry table) get no over-paint — the 3-bit PNG's time text stands until the first partial wipes it — and `last_drawn_phrase_min` is set to `0xffff` so the next partial knows it's in the cold state.

Vertical centering: each phrase bitmap is tight-bbox-cropped around its ink pixels. The firmware blits at `(clock_zone_x, clock_zone_y + (clock_zone_h - bitmap.height) / 2)` so phrases of differing ink heights (e.g. ascender-heavy "quarter past eleven" vs lowercase-only "half past two") sit in the centered position within the renderer's 220u flex container.

#### Scenario: Partial wake at 22:15 in Night blits "quarter past ten"

- **WHEN** the device is in Night mode (current_mode = Night), the schedule has `night: 60/0/15` (Full at every :00, partial at :15/:30/:45), and a Timer wake fires at 22:15
- **THEN** `planWake` returns `Path::Partial`; the Night branch of `doPartial` calls `phraseForMinute(22*60+15)` and gets the "quarter past ten" bitmap; if cold state (last_drawn_phrase_min == 0xffff) pulses zone black first, otherwise seeds with the prior phrase; blits the new bitmap; runs `partialUpdate1Bit`; updates `last_drawn_phrase_min` to `1335`; returns `true`. The Full path is NOT promoted

#### Scenario: Non-partial-eligible minute returns null

- **WHEN** a Timer wake fires at 03:07 in Night (not a 15/30/45 boundary)
- **THEN** `planWake` returns `Path::Skip` (Night `60/0/15` has no cadence at :07); `doPartial` is never called. As a defensive check, if a contrived path did call `phraseForMinute(3*60+7)`, it returns `nullptr` and `doPartial` returns false

#### Scenario: Top-of-hour Night Full does not over-paint

- **WHEN** a Full wake fires at 03:00 in Night mode
- **THEN** the 3-bit PNG paints "three o'clock" (or whatever the renderer's time-text rendering is); the post-Full cleanup looks up `phraseForMinute(180)` and gets `nullptr` (03:00 is a Full, not a partial slot); the over-paint step is skipped; the panel shows the PNG's rendering

### Requirement: `Persisted` carries `last_drawn_phrase_min` across deep sleep

`fw::wake::Persisted` SHALL include a `uint16_t last_drawn_phrase_min` field, initialised to `0xffff` (sentinel: "nothing drawn yet"). The field is updated by `doPartial`'s Night branch and `doFull`'s post-cleanup Night branch whenever a phrase bitmap is drawn. It survives deep sleep so subsequent partial wakes' seed step uses the right "previous" image.

#### Scenario: Sequential Night partials seed from the prior phrase

- **WHEN** the device draws the 22:15 phrase, deep-sleeps, wakes 15 min later for the 22:30 partial
- **THEN** `doPartial` looks up the 22:15 phrase via `last_drawn_phrase_min == 1335`, blits it as the seed, runs `partialUpdate1Bit` (visually a no-op since 22:15 was already on the panel), then blits the 22:30 phrase and runs the second `partialUpdate1Bit`. The library's diff produces correct black-to-white "clear" pulses for any 22:15 pixels that 22:30 doesn't cover, and black-paint pulses for new 22:30 pixels — clean, ghost-free transition

#### Scenario: First Night partial after cold boot has no seed

- **WHEN** the device cold-boots, RTC slow memory is wiped, `last_drawn_phrase_min == 0xffff`, then runs a Full at 22:00 followed by a partial at 22:15
- **THEN** the 22:00 Full's PNG renders "ten o'clock" in 3-bit; the post-cleanup sets `last_drawn_phrase_min = 0xffff` and does no over-paint (22:00 is not in the 25-phrase set). On the 22:15 partial, `doPartial` sees the cold state, pulses the phrase zone solid black via `fillRect1Bit + partialUpdate1Bit` to wipe the 3-bit AA pixels, then blits "quarter past ten" + `partialUpdate1Bit`. The cold-state wipe adds one extra ~150 ms partial update once per Night cycle (first partial after every Full). Subsequent partials use the seed-then-draw warm path
