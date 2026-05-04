# Design — Grounded Stars cell

## Goal

The Stars cell becomes a single short statement rendered at a tiered
font size. It is sourced from real ephemerides (Skyfield) plus the
day's space-launch and space-news feeds, with Haiku acting only as a
phrasing layer over a structured fact-block. The cell's visible text
is therefore always grounded in computable data; the LLM cannot invent
events that aren't in the fact-block.

## Architecture

```
                          ┌─────────────────────────┐
                          │  ha/scripts/             │
                          │  generate_astro_event.py │
                          │                          │
  Skyfield ── ephemerides ──▶                       │
  LL2 ─────── upcoming   ──▶  build fact-block ──▶  │  Haiku call
  SFN/NSF ─── RSS top    ──▶                       │  (single
                          │                          │   statement,
                          │  parse + length-check ◀──┘   ≤ ~90c)
                          │              │
                          │              ▼
                          │   astro_event.txt (state file)
                          └──────────────│──────────
                                         ▼
              command_line_sensor (with mtime freshness guard)
                                         ▼
              publish_inputs.yaml → renderer/inputs/weather.json
                                         ▼
              renderer/src/modes/weather.ts
                  ├── pickStarsTier(statement) → font tier 1-7
                  └── render <div class="value" data-fit-tier="N">
                                         ▼
                            weather.css tier rules
                                         ▼
                                  Weather face PNG
```

## Tier table (renderer)

```
[tier, font(u), line-height(u), soft-cpl, max-visual-lines]
T1   30u   36u   23   2
T2   28u   34u   25   2
T3   27u   32u   26   2
T4   26u   32u   27   2
T5   25u   30u   28   3   ← floor (matches Moon cell font size)
T6   22u   28u   32   3   ← sub-floor escape (rare)
T7   20u   26u   35   3   ← sub-floor escape (very rare)
```

Soft-cpl is calibrated for IBM Plex Sans 500 at ≈ 0.51× font-size per
char advance on English mixed-case prose. May need tuning after the
first real renders; calibration shows up as wrap-at-shorter-than-cpl
on the rendered PNG.

### Picker behaviour

| Char count | Tier | Visual |
|---:|---|---|
| ≤ 23 | T1 | 30u, 1 line |
| 24–25 | T2 | 28u, 1 line |
| 26 | T3 | 27u, 1 line |
| 27 | T4 | 26u, 1 line |
| 28 | T5 | 25u, 1 line |
| 29–46 | T1 | 30u, 2 lines (wrap) |
| 47–50 | T2 | 28u, 2 lines |
| 51–54 | T3-T4 | 26-27u, 2 lines |
| 55–56 | T5 | 25u, 2 lines |
| 57–84 | T5 | 25u, 3 lines |
| 85–96 | T6 | 22u, 3 lines |
| 97–105 | T7 | 20u, 3 lines |
| > 105 | T7 + CSS overflow trim |

Floor stays at 25u for everything up through 84 chars. Sub-floor tiers
(T6, T7) are a safety valve, not the working range — observed Haiku
outputs in our experiments stayed within 60–70 chars in the worst case.

## Fact-block shape

```jsonc
{
  "today_utc": "2026-04-30T07:00Z",
  "sky_tonight": {
    "date": "...", "location": "Bucharest (44.43N, 26.10E)",
    "tz": "EEST (UTC+3)",
    "sun": {"set": "20:18", "rise_next": "06:06"},
    "twilight": {"astronomical_night_starts": "22:13", ...},
    "moon": {"phase": "full moon", "illumination_pct": 99,
             "set": "05:28", "up_during_window": "all night"},
    "planets": [
      {"name": "Jupiter", "visible": true,
       "window_local": "20:18-01:03", "peak_alt_deg": 54.7,
       "direction_at_peak": "SW"}, ...
    ],
    "close_approaches_under_5deg": [],
    "active_meteor_showers": [
      {"name": "eta-Aquariids", "active": "04-19 to 05-28",
       "peak_date": "2026-05-06", "zhr": 50, "days_to_peak": 6}
    ]
  },
  "upcoming_launches_next_10": [
    {"net_utc": "...", "name": "Falcon 9 Block 5 | Starlink Group 10-38",
     "provider": "SpaceX", "pad": "...", "country": "USA",
     "status": "Go", "mission_type": "Communications"}, ...
  ],
  "recent_space_news": {
    "spaceflight_now": [{"title": "...", "pub": "..."}, ...],
    "nasaspaceflight": [{"title": "...", "pub": "..."}, ...]
  }
}
```

The block is passed verbatim to Haiku. Salience ranking is delegated to
the model — pre-filtering or pre-ranking on the Python side risks
removing context the model needs (e.g., a full moon caveat that lets it
correctly skip a meteor shower).

## Prompt shape

The prompt names the reader explicitly:

> You write the "Stars" cell of a small e-ink kitchen panel for a single
> reader: a stargazer who loves astronomy and space science.

It forbids mentioning the moon (the Moon cell handles that), gives
ranking guidance (routine Starlink = noise, crewed/lunar/Mars/novel
vehicles = high), forbids stories older than ~7 days, and demands strict
JSON output. Hard constraints: text ≤ 70 characters (soft target;
renderer's tier table absorbs up to ~84 at the floor), no emoji, no
"Tonight" prefix.

## Salience verification

Two scenarios were exercised against the live API while drafting:

| Scenario | Sky data | Top news | Haiku pick |
|---|---|---|---|
| **Real** (2026-04-30) | Jupiter high in SW until 01:00, full moon up all night, eta-Aquariids active but moon-washed | Falcon Heavy returned 1d ago, Artemis III core-stage arrived 2d ago | "Jupiter high in southwest at 54 degrees" — sky wins because news items are past tense |
| **Inverse** (fabricated) | All planets behind sun, no meteors | "Artemis IV launches tomorrow — first crewed lunar landing since 1972" | News wins; Haiku correctly identifies the lunar-return milestone over a quiet sky |

The model also correctly suppressed eta-Aquariids without being told to
("active but heavily suppressed by the full moon") and never mentioned
the moon despite it being in the fact-block.

## Output validation

Haiku consistently wraps JSON in a markdown fence despite explicit
prompt instructions. The Python helper strips fences and falls back to
a deterministic Skyfield-derived phrase if parsing fails, so the panel
never displays raw model output that wasn't validated.

Length validation is soft — over-budget text passes through to the
renderer's tier table, which is designed to absorb up to ~84 chars at
the floor. The model is asked to stay ≤ 70 but is not retried on
modest overflow; the cell handles it.

## Freshness guard

The current command-line sensor returns the file contents blindly. If
the cron silently fails one day, the panel keeps showing yesterday's
text indefinitely. The new sensor reads the file and the file's mtime;
if mtime is older than 30 hours, it returns the empty string, which
the renderer then surfaces as "no event tonight."

## Failure modes and fallbacks

| Failure | Fallback |
|---|---|
| Skyfield import fails | Emit fallback phrase based on `sensor.moon_phase_name` (the old behavior, simplified; no Haiku call). Log warning. |
| LL2 / RSS fetch fails | Continue without that data; Haiku ranks among what it has. |
| Haiku call fails or returns invalid JSON | Emit Skyfield-derived deterministic phrase: highest-altitude-and-magnitude visible planet, e.g. "Jupiter high in SW until 01:00". |
| All upstream fetches fail | Emit "—" (em-dash). Cell renders the literal "no event tonight" treatment. |

## Non-goals

- ISS pass surfacing on the cell. Possible technically (Skyfield + TLE
  from celestrak), but the panel's daily refresh cadence is wrong for
  pass times that drift hour by hour.
- Multi-language output. The cell is English-only today; localisation
  is a separate concern.
- Removing the legacy moon-phase fallback table from `generate_astro_event.sh`
  in this change. The shell script is being replaced wholesale; the
  table goes with it.
