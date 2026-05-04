# Tasks — Grounded Stars cell

## 1. Renderer (already done)

- [x] 1.1 `renderer/src/zones.ts`: widen `astro_event` to maxChars 90 / maxLines 4; comment marks zone as backstop.
- [x] 1.2 `renderer/src/modes/schema.ts`: make `astro.event.detail` optional.
- [x] 1.3 `renderer/src/modes/weather.ts`: drop the title/detail split in the Stars cell; add `STARS_TIERS` table and `pickStarsTier()`; render `<div class="value" data-fit-tier="N">`.
- [x] 1.4 `renderer/templates/weather/weather.css`: replace static `.value` size with seven tier-keyed rules (T1=30u → T7=20u); remove `.detail` rules; family is `var(--font-sans)`, weight 500.
- [x] 1.5 `npx tsc --noEmit` clean for the edited files.

## 2. HA-side helper

- [x] 2.1 New file `ha/scripts/generate_astro_event.py` — Skyfield + LL2 + RSS + Haiku phrasing + fence-strip parse + Skyfield-derived fallback + write to state file. Smoke-tested end-to-end against live Bucharest data and a fabricated Artemis-IV fact-block.
- [ ] 2.2 Operator-VM step: drop `de421.bsp` (~17 MB) at `/config/custom/inkplate/data/de421.bsp`. Local dev copy is at `/tmp/astro/de421.bsp`. Suggested fetch: `curl -L https://ssd.jpl.nasa.gov/ftp/eph/planets/bsp/de421.bsp -o /config/custom/inkplate/data/de421.bsp`.
- [x] 2.3 Removed dead `ha/scripts/generate_astro_event.sh`; the Python helper is now the entrypoint and HA invokes it directly.
- [ ] 2.4 Operator-VM step: `pip install skyfield` in the Python environment HA's `command_line` shell uses.

## 3. HA wiring

- [x] 3.1 `ha/automations/astro_event.yaml` cron moved 17:00 → 07:00; variables simplified (no longer passes `moon_phase`; passes `tz_offset` derived from `now().utcoffset()`).
- [x] 3.2 `ha/integrations/command_line_sensors.yaml` freshness guard: returns empty when `astro_event.txt` mtime > 30 h (108 000 s). Verified locally against fresh / stale / missing fixtures. Shell uses `stat -c %Y || stat -f %m` so it works on both GNU and BSD stat.
- [x] 3.3 `ha/automations/publish_inputs.yaml` no longer publishes `astro.event.detail`. Renderer schema treats it as optional anyway.
- [x] 3.4 `ha/integrations/shell_commands.yaml` invokes `python3 generate_astro_event.py --lat ... --lon ... --tz-offset ...`.

## 4. e2e smoke

- [x] 4.1 Helper run with live Bucharest data → "Jupiter high in SW until 01:03, Venus low in W until 22:03" (58 ch).
- [x] 4.2 Helper run with fabricated Artemis-IV fact-block → "Artemis IV launches tomorrow—first crewed lunar landing in 54 years" (67 ch).
- [x] 4.3 PNGs rendered against test renderer (port 8585): short/medium/real/inverse. All tiers match prediction (T1/T1/T5/T5). Cell footprint stays within envelope.
- [x] 4.4 Moon cell unchanged in all four renders; Stars never mentions the moon despite the moon being present in the fact-block.

## 5. Spec deltas

- [x] 5.1 `dashboard-faces` delta: budget table — `astro_event` row updated, `astro_detail` row marked DEPRECATED; "Stars cell layout" requirement added; "Astro event freshness guard" scenario added.
- [x] 5.2 `ha-integrations` delta: rewrite "Astro data" requirement to enumerate Skyfield + Launch Library 2 + RSS as inputs; add freshness-guard scenario; bump cron to 07:00.

## 6. Validation and archive

- [x] 6.1 `openspec validate add-grounded-stars-cell` passes.
- [x] 6.2 e2e smoke renders reviewed by operator — typography signed off ("the typography is ok").
- [x] 6.3 Archive at operator request after dev-side wiring lands; one-full-day-cycle soak shifts to operator-VM follow-up (tasks 2.2 and 2.4 below).

### Operator-VM follow-ups (out of scope of this archive — pre-existing operator-machine workflow)

- [ ] 2.2 Drop `de421.bsp` (~17 MB) at `/config/custom/inkplate/data/de421.bsp`. Suggested: `curl -L https://ssd.jpl.nasa.gov/ftp/eph/planets/bsp/de421.bsp -o /config/custom/inkplate/data/de421.bsp`.
- [ ] 2.4 `pip install skyfield` in the Python environment HA's `command_line` shell uses.

These two steps must be done on the operator VM before the 07:00 cron will succeed; until then the helper falls through to its empty-state branch and the cell renders "no event tonight" via the freshness guard.
