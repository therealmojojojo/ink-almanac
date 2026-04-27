## Why

The 0-60 minute precipitation nowcast currently comes from Open-Meteo's `minutely_15` endpoint — 15-minute buckets with model-derived precipitation (ICON-D2 for Central/Eastern Europe, not radar-augmented). That was the right call when we committed to "no API keys" but the UX ceiling is low: 15-minute granularity means "RAIN IN 15 MIN" can actually be anywhere between 0-29 minutes away, and the model can miss ongoing drizzle that a radar-fed source catches.

The operator now has an OpenWeatherMap OneCall 3.0 key. OWM's `minutely` field gives a rolling 60-minute window at **1-minute resolution** with radar augmentation where coverage exists (including Romania), and the free tier comfortably covers our call budget. This change switches the minutely source from Open-Meteo to OWM, rolls out the new 1-minute labels ("RAIN IN 8 MIN", "CLEARING IN 23 MIN"), and — importantly — adds the nowcast line to the Weather face, which previously didn't render the label at all despite being the face most relevant to rain.

## What Changes

- **New secret**: `openweathermap_api_key` in `ha/secrets.yaml` and `secrets.yaml.example`. Supersedes the "OWM dropped" note in `add-ha-integrations/tasks.md:19`; operator reversed that decision now that minute-level precision is on the table.
- **Minutely source**: `ha/integrations/weather_nowcast_minutely.yaml` rewritten to poll OWM OneCall 3.0 (`data/3.0/onecall?exclude=current,hourly,daily,alerts&units=metric`) every 5 minutes per location. Sensor name changes from `*_openmeteo_minutely` to `*_owm_minutely`. Open-Meteo is no longer called — MET.no remains the hourly fallback inside the combiner.
- **Label granularity**: 1-minute buckets replace 15-minute buckets. Labels now read "RAIN IN 8 MIN" instead of rounded-to-quarter. Threshold unchanged (≥ 0.1 mm/h == wet).
- **Weather face**: `renderer/src/modes/weather.ts`'s `renderRow` now emits a `.nowcast` `<div>` under `.cond`, per location. `renderer/templates/weather/weather.css` gains a matching rule (mono-caps, 20u, `--mid` tone). The Summary face already renders this label (no change).
- **Primary for conditions/hourly remains MET.no.** OWM is wired only for minutely precipitation to keep the surface small and the call budget low.

## Capabilities

### Modified Capabilities

- `ha-integrations`: minute-level precipitation nowcast now comes from OWM; `openweathermap_api_key` is required; Open-Meteo sensor `*_openmeteo_minutely` no longer exists.
- `dashboard-faces`: Weather face renders `weather.locations[].nowcast.label` when present.

## Impact

- **Files edited**:
  - `ha/secrets.yaml` — new `openweathermap_api_key`.
  - `ha/secrets.yaml.example` — template line with the signup URL.
  - `ha/integrations/weather_nowcast_minutely.yaml` — full rewrite, OWM-based.
  - `ha/docs/secrets-checklist.md` — `openweathermap_api_key` row marked "always" with the new role.
  - `ha/docs/architecture.md` — component diagram updated ("OWM OneCall 3.0 1-min"; dropped "OWM fallback" from the weather row since OWM now fills a different role).
  - `renderer/src/modes/weather.ts` — adds `.nowcast` markup inside `.current`.
  - `renderer/templates/weather/weather.css` — adds `.weather-row .current .nowcast` rule.
- **No firmware change**. Device still fetches `/display/{mode}.png` and the new label just falls inside the existing zone geometry.
- **Rate-limit budget**: 2 locations × 12 polls/hour × 24 = 576 calls/day of 1000 free-tier — 58% utilization, comfortable headroom. If we ever bring a third location online or shorten the poll interval, revisit.
- **Deploy**: standard `make deploy-ha`. First OWM poll happens within 5 min of HA restart.

## Relationship to earlier "DROPPED" decision

`openspec/changes/add-ha-integrations/tasks.md:19` said OWM fallback was dropped because "simpler, no extra key, acceptable degradation when MET.no is unreachable." That remains true for fallback — we don't re-introduce OWM as a fallback here. OWM fills a **different** role now: it's the primary (and only) source of minute-level precipitation. MET.no cannot provide minute precision; the ceiling isn't MET.no reliability, it's MET.no resolution. Different trade, different decision.
