# Add Night text-clock partial refreshes (and pool-only poetic line)

> **Status — 2026-05-19**: re-audited; still applicable, still no code. All preconditions hold:
> - Night's `partial_min` is still `15` (per `ha/config/wake_schedule.yaml:65`) so the 25 partials per night still fail or no-op as described.
> - The renderer's `GET /display/night/clock-zone.json` still returns **404**.
> - Firmware has zero hits for `night_phrase`, `phraseForMinute`, or `bake-night-phrases`.
> - The bake-precedent tool `renderer/src/tools/bake-clock-glyphs.ts` (400 lines) is intact; generated `firmware/src/generated/clock_glyphs.{h,cpp}` are intact.
> - `ha/scripts/generate_poetic_weather_line.sh` still hits `api.anthropic.com/v1/messages` (model bumped to `claude-haiku-4-5-20251001` since the proposal was drafted; otherwise unchanged).
>
> Three small drifts since 2026-05-05:
> 1. **Pool is already richer than the proposal targets.** Today: **8 lines × 14 buckets = 112 entries** in `ha/config/night_fallback_lines.yaml`. Proposal target was "5 × 13 = 65." The "expand pool" step is mostly done; the rename + voice-check are what's left.
> 2. **`renderer/src/modes/night.ts::nightPhrase(h, m)` already produces the exact 25-phrase vocabulary the bake tool needs.** The proposal hardcodes the phrase list in the bake tool; the cleaner alternative is to call the renderer's existing `nightPhrase()` directly so renderer and firmware stay in lockstep. Single source of truth, no drift.
> 3. **Flash budget is essentially unchanged: 81.9% today** (1,072,937 / 1,310,720 bytes), vs the 82.0% in the proposal. The +150 KB phrase-bitmap estimate still lands at ~93%. Headroom analysis holds.
>
> Supersedes the unimplemented `replace-poetic-llm-with-pool` (whose directory no longer exists in `openspec/changes/`).

## Why

Two related Night-mode problems, bundled into one change because they
touch the same surface (the Night face's content pipeline) and ship
together.

### 1. Night has no clock partial cadence today

The schedule planner now supports per-tier `partial_min`
(`add-pushable-wake-schedule`) and the operator's live config sets
**Night to `60/0/15`** — Full at the top of every hour, partial at
:15 / :30 / :45. But the Night face's clock is rendered as a **text
phrase** ("quarter to three"), not "HH:MM" digits. The existing
partial-refresh path (`firmware/src/clock_render.cpp` +
`firmware/src/generated/clock_glyphs.{h,cpp}`) composes the clock from
**baked Fraunces digit glyphs** — 0..9 plus colon. That pipeline
cannot render English-language fuzzy-time phrases.

So today, `60/0/15` produces 25 partial wakes per night that fail —
`doPartial` returns false (no baked preset for Night's clock font),
and the wake either skips silently (Poll path with no preset) or
falls through to a Full (Partial path). Either way, Night gets no
benefit from its 15-min partial cadence.

### 2. The poetic-line LLM call is overkill

`ha/scripts/generate_poetic_weather_line.sh` currently calls Claude
Haiku once per hour with the current weather bucket and asks for an
English short observational line. The script falls back to the
hand-curated pool in `ha/config/night_fallback_lines.yaml` on any
failure or schema-rejection.

Two practical issues:

- The LLM occasionally produces Romanian (the schema allows Romanian
  diacritics) with **misspellings** that pass the regex validator but
  read badly on the panel.
- Cost: one Anthropic API request and one internet round-trip every
  hour, for a feature whose pool is already curated, voice-checked,
  and large enough to rotate without obvious repetition.

The fallback path is already the high-quality path. Make it the
only path.

## What Changes

### A. Bake 25 phrase bitmaps into firmware flash

The Night clock vocabulary is **fixed**: 25 phrases for the partial
cadence's eligible minutes, expressed in plain lowercase English with
"midnight" replacing "twelve" at the 00:00 hour:

```
22:15 quarter past ten        02:15 quarter past two
22:30 half past ten           02:30 half past two
22:45 quarter to eleven       02:45 quarter to three
23:15 quarter past eleven     03:15 quarter past three
23:30 half past eleven        03:30 half past three
23:45 quarter to midnight     03:45 quarter to four
00:15 quarter past midnight   04:15 quarter past four
00:30 half past midnight      04:30 half past four
00:45 quarter to one          04:45 quarter to five
01:15 quarter past one        05:15 quarter past five
01:30 half past one           05:30 half past five
01:45 quarter to two          05:45 quarter to six
                              06:15 quarter past six
```

A new build-time tool `renderer/src/tools/bake-night-phrases.ts`
(parallel to the existing `bake-clock-glyphs.ts`) renders each phrase
via Playwright at the Night face's CSS-defined clock font / size /
style, thresholds to 1-bit, packs into a binary table, and emits
`firmware/src/generated/night_phrases.{h,cpp}` with:

The bake tool SHOULD source the 25 phrases by importing
`renderer/src/modes/night.ts::nightPhrase(h, m)` and iterating
`for m_of_day in 22*60..(6*60+30) step 15 where m_of_day % 15 == 0`
rather than hardcoding the phrase list. The renderer already owns
the canonical phrase vocabulary; reusing the function keeps the
runtime PNG and the baked bitmaps lockstep-consistent. (The proposal
originally hardcoded the list; reuse was identified during the
2026-05-19 audit.)

- A `NightPhraseBitmap` struct (`width`, `height`, `data` ptr).
- A `phraseForMinute(int min_of_day) → const NightPhraseBitmap*` lookup.
  Returns `nullptr` for any minute outside the 25-entry partial set.

Storage cost: each phrase ~600×80 px 1-bit ≈ 6 KB; 25 phrases ≈
**150 KB** added to the firmware binary. Current flash usage is
82.0% / 1310720 B; this brings it to ~93%. Acceptable headroom.

Why bake at build time rather than fetch from the renderer at runtime:
the partial cadence requires the bitmaps to be available across deep
sleep (between an hourly Full and the next 15-min partial). PSRAM is
volatile across deep sleep on the Inkplate, default NVS partition is
~24 KB (too small for 150 KB), and a custom partition would add
unnecessary complexity for a vocabulary that **never changes** by
design. Baking is the simplest durable choice.

### B. Renderer Night clock-zone

`GET /display/night/clock-zone.json` currently returns 404 (Night has
no clock element the firmware can compose locally). After this change:

- Returns `{x, y, w, h, font_size}` for the rectangle the firmware
  should treat as the phrase zone.
- `font_size` field is decorative (the firmware uses the baked phrase
  bitmaps' inherent dimensions); the firmware uses (x, y) for the
  blit anchor and (w, h) only for the post-Full cleanup pulse.

The Night PNG continues to render the time text as part of the
3-bit raster (operator may decide to drop it later, but keeping it
for now means a fallback if the firmware partial path fails).

### C. Firmware partial dispatch for Night

- `firmware/src/main_loop.cpp::doPartial` extended: when
  `current_mode == Night`, look up `phraseForMinute(local_min_of_day)`.
  Non-null → blit the bitmap to (x, y), partialUpdate1Bit. Null →
  return false (Partial wake at a non-15-min boundary, e.g., a
  manual minute-tick on a different schedule — caller handles).
- `firmware/src/main_loop.cpp::doFull` post-Full cleanup, when
  `active == Night`: pulse the phrase rectangle solid black + white,
  then blit the current minute's phrase bitmap (or nothing if the
  Full minute itself isn't in the 25-phrase set — at the top of the
  hour Night Fulls show "[hour] o'clock" via the rendered PNG).
- `firmware/src/clock_render.cpp` (or sibling): a thin
  `nightPhrase::draw(panel, x, y, min_of_day)` that wraps the
  bitmap blit.

### D. Pool-only poetic line (subsumes `replace-poetic-llm-with-pool`)

- **Rename**: `ha/config/night_fallback_lines.yaml` →
  `ha/config/night_poetic_pool.yaml`. The file is no longer a
  "fallback"; it's the only source of truth.
- **Pool contents — already largely in place.** As of 2026-05-19 the
  pool holds **8 lines × 14 buckets = 112 entries** (clear_cold,
  clear_mild, clear_warm, partly_cloudy, cloudy, cloudy_cold, fog,
  drizzle, rain, pouring, thunderstorm, snow, sleet, windy_dry). The
  proposal's "5 × 13 = 65" target is already exceeded. Remaining work
  in this section is: (a) the rename; (b) drop Romanian-diacritic
  support from the validator (no current entry uses Romanian so this
  is a no-op for content); (c) voice-check the existing entries once
  more before they become the only source.
- **Slim the picker**: `ha/scripts/generate_poetic_weather_line.sh`
  becomes a ~40-LOC pool-picker — drop the API key load, request body,
  response parsing, and length-clamping. Validate length + charset
  (English ASCII subset), `random.choice` from `pool[bucket] or
  pool['cloudy'] or ['Quiet night.']`, write to
  `state/poetic_weather.txt`.
- **Trigger model**: bucket-change instead of hourly. New template
  sensor `sensor.inkplate_night_poetic_bucket` (existing bucket logic
  moved into the sensor); `ha/automations/poetic_weather.yaml` fires
  on `state_changed` of that sensor + on `homeassistant.start`. As
  long as the bucket stays the same, the same line stays on the
  panel — no churn during stable weather.
- **Delete** `ha/config/poetic_weather_line.yaml` (provider/model
  config no longer read). Keep `ha/secrets.yaml`'s
  `anthropic_api_key` — it's still used by `generate_astro_event.py`.

### E. Out of scope

- **Operator-editable phrasing.** The 25 fuzzy-time phrases are baked
  into firmware flash. Changing them requires a re-bake and re-flash.
  Acceptable: the vocabulary is deterministic, language-fixed
  (English), and unlikely to change.
- **Per-locale phrasing.** No Romanian / Spanish / etc. variants.
  English-only, hardcoded at build time.
- **Runtime fetch of phrase bitmaps.** Considered and rejected (see
  rationale in Section A).
- **Removing the time text from the Night PNG.** The Full PNG keeps
  rendering the time as part of its 3-bit raster, partly as a
  fallback (if firmware partial path ever fails the panel still shows
  the right time at top-of-hour) and partly because removing it would
  require a renderer-side CSS rework that isn't warranted.

## Why now

The `60/0/15` schedule was deployed today (2026-05-05). The 15-min
partial cadence currently does no useful work in Night mode (no baked
clock zone). Either fix it forward (this change) or revert Night to
`60/0/0` to avoid empty wakes. Fixing forward is the right move —
the Night clock is the most-watched face in the kitchen at the time
the operator is most likely to glance at it.

The poetic-line cleanup is bundled because the same review +
deploy + flash cycle covers both, and the LLM removal has been a
month-old should-do that hasn't shipped on its own.

## Risks

1. **Flash-budget creep.** 150 KB phrase bitmaps push flash from 82%
   to ~93%. Mitigations: aggressive 1-bit thresholding (no
   anti-aliasing storage), tight bounding boxes per phrase, single
   shared dimension per phrase row (so we can store stride implicitly).
2. **Font/style drift.** If the renderer's Night CSS changes, the
   baked bitmaps no longer match the rest of the face. Mitigation:
   the bake tool reads the Night CSS at build time, and the build
   step regenerates `night_phrases.{h,cpp}` whenever Night CSS or the
   phrase list changes (CMake / npm script dep on those inputs).
3. **Phrase-zone coordinates drift.** If the Night face's layout
   moves the clock zone, partials would draw at the wrong place.
   Mitigation: the renderer's `clock-zone.json` is the canonical
   (x, y); firmware re-fetches every Full (existing behavior for
   other modes). A layout move propagates correctly.
4. **First Night Full after firmware update on a clear-sky 03:00.**
   The Full's PNG includes the time-text rendered at 03:00. The
   firmware then over-paints "three o'clock" — but 03:00 is a Full,
   not a partial slot, and the 25-phrase table doesn't include it.
   Resolution: at top-of-hour Fulls, the firmware does NOT over-paint
   (the PNG handles it). The over-paint only fires on partial wakes
   (15 / 30 / 45 minutes past).
