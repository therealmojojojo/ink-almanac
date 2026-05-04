# Replace the Night-poetic-line LLM call with a curated English-only pool

> **Status — 2026-05-04**: proposed; no code yet.

## Why

The Night face's poetic line is currently produced by `ha/scripts/generate_poetic_weather_line.sh`, which calls Claude Haiku once per hour with the current weather bucket and asks for a short observational line in the project's house voice. The script falls back to a curated pool (`ha/config/night_fallback_lines.yaml`) on any failure or schema-rejection.

Two problems with the LLM-primary path in practice:

1. **Romanian-language failures.** The schema allows Romanian diacritics in case the model outputs Romanian. In practice the model sometimes does — and produces lines with **misspellings** that pass the regex validator but read badly on the panel. The operator has no per-language quality gate; broken Romanian gets through.
2. **Cost without benefit.** The pool is already curated, voice-checked, and large enough to rotate without obvious repetition. Each hourly LLM call costs an Anthropic API request, an internet round-trip, and risk of API/network failure. The curated pool produces strictly better-quality lines deterministically.

The fallback path is already the high-quality path. Make it the only path.

## What Changes

### A. Drop the LLM call

`ha/scripts/generate_poetic_weather_line.sh` becomes a tiny pool-picker:
1. Read bucket arg.
2. Open `ha/config/night_poetic_pool.yaml` (renamed from `night_fallback_lines.yaml` — the file is no longer a "fallback").
3. `random.choice(pool[bucket] or pool['cloudy'] or ['Quiet night.'])`.
4. Validate length + charset (English ASCII only; see schema below).
5. Write to `state/poetic_weather.txt`.

The Anthropic API key path, response parsing, length-clamping, and fallback decision tree are all removed. Script shrinks from ~200 lines to ~40.

### A.1. Trigger model — re-pick on bucket change, not hourly

The current automation re-rolls the line every hour even when nothing has changed. With a deterministic pool, that just produces visible churn for no reason: a Night face that quietly shows the same sky for hours has the line flip on the hour to a different sentence about the same condition.

Replace the hourly trigger with a **bucket-change** trigger:

- Add a template sensor `sensor.inkplate_night_poetic_bucket` whose state is the bucket key computed from the current weather (existing template logic moves into this sensor).
- The automation fires on `state_changed` of that sensor (`unknown` / `unavailable` → bucket and bucket → bucket transitions).
- On fire: pick a new line for the new bucket, write to the state file.
- Keep one safety trigger on `homeassistant.start` so HA restarts repopulate the line.

Net behavior: as long as `clear_cold` stays `clear_cold` for 8 hours, the same sentence stays on the panel. When weather shifts to `partly_cloudy`, one new line is picked from that bucket and stays until the next bucket change.

### B. English-only pool

`ha/config/night_poetic_pool.yaml` (renamed) has new schema rules:

- Each line is **ASCII letters, digits, spaces, and the punctuation set `,.:;!-'"`** — no Romanian diacritics, no emoji, no curly quotes, no em-dashes.
- ≤ **40 graphemes** (matches the renderer's `poetic_line` zone). Existing pool entries are 32-char-targeted; they still fit.
- House voice unchanged: plain, observational, slightly melancholy.

Existing entries are already English; the schema change just removes the *option* of Romanian (which has been a quality liability).

### C. Bucket selection unchanged

The HA automation `inkplate_poetic_weather_hourly` keeps its existing template logic that maps `condition + temp + wind` to a bucket name (`clear_cold`, `clear_mild`, `partly_cloudy`, `cloudy`, `cloudy_cold`, `fog`, `rain`, `pouring`, `thunderstorm`, `snow`, `sleet`, `windy_dry`). The bucket key is passed to the script unchanged.

### D. Pool growth (operator follow-up)

To avoid noticeable repetition with hourly rotation, each bucket should ideally have **8-15 entries**. Today's pool meets this for common buckets (clear_*, partly_cloudy, cloudy) but is thinner for rarer ones (sleet, thunderstorm, fog). An operator follow-up — not part of this change — is to expand the underweight buckets.

## Out of Scope

- **Multi-language support.** English only. If we ever want a Romanian variant we add a `night_poetic_pool_ro.yaml` and a language selector — separate change.
- **Time-of-night buckets.** "It's 3 AM" doesn't get a different line from "It's 11 PM"; they come from the same bucket. Could be a future axis (e.g., late-night vs. early-night flavors). Not now.
- **Renderer-side changes.** Zero. The renderer just reads `state/poetic_weather.txt` via `sensor.inkplate_poetic_weather_line`.
- **`anthropic_api_key` removal from secrets.** The key stays — `generate_astro_event.py` still uses it for the Stars-cell phrasing layer.
- **Backward-compatible LLM fallback.** No "if pool empty fall back to LLM" — pool is the source of truth.

## Risks

- **Repetition becomes more visible.** Today the LLM provides variety alongside the pool; deterministic pool selection will repeat lines after ~bucket-size hours of the same weather. Mitigation: the random seed is genuinely random per call, so repetition is bounded by birthday-paradox math (≥ 8 entries → < 50 % repeat in 8 hours).
- **A bucket with stale lines becomes obvious.** Today the LLM "freshens" things even if pool is stale. Without LLM, an unused bucket's lines persist. Mitigation: this is operator hygiene, not a code problem.
- **Existing automations + state-file path are unchanged**, so no migration steps for the device. Only the script body and the pool filename change.
