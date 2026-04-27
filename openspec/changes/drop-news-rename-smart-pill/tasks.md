# Tasks — Drop news, rename smart-pill plumbing

## 1. Resolve the schema-shape question

- [ ] 1.1 Operator decides: flatten `news.json` to `{body: "…"}` (recommended) or preserve the `{count, items: [{body}]}` wrapper. Tasks below assume flatten; revise §3.1 and §4.1 if the operator chooses preserve.

## 2. Delete dead news infrastructure (Refactor 1)

- [ ] 2.1 Delete `ha/config/news_sources.yaml`
- [ ] 2.2 Delete `ha/sensors/news_sources.yaml`
- [ ] 2.3 Delete `ha/scripts/generate_news_sensors.py`
- [ ] 2.4 Edit `ha/deploy.sh` to remove the "Regenerate per-source news sensors" block (~5 lines)
- [ ] 2.5 Run `bash -n ha/deploy.sh` to confirm no syntax error after the edit

## 3. Renderer rename (Refactor 2)

- [ ] 3.1 `renderer/src/modes/schema.ts`: rename `newsInput` to `smartPillInput`. If flattening (§1.1), shape becomes `z.object({ body: z.string().optional() })`. Field on `summaryInput` becomes `smart_pill`
- [ ] 3.2 `renderer/src/modes/summary.ts`: update field accesses; replace `applyZone('news_body', …)` with `applyZone('smart_pill_body', …)`; update placeholder branch to check `input.smart_pill?.body`
- [ ] 3.3 `renderer/src/modes/index.ts`: replace `requireInput('news')` with `requireInput('smart_pill')`
- [ ] 3.4 `renderer/src/server.ts`: replace `'news'` with `'smart_pill'` in inputs allowlist
- [ ] 3.5 `renderer/src/zones.ts`: rename `news_body` zone to `smart_pill_body`
- [ ] 3.6 `renderer/templates/summary/summary.css`:
  - Drop the `.news` wrapper class from selectors (`.summary-smart-pill .news .item .body` → `.summary-smart-pill .body`)
  - Drop the `b = news-only / c = climate-dominant` historical comment at the file head
- [ ] 3.7 Rename test fixtures: `renderer/test/fixtures/news.json` → `smart_pill.json` (and any `degraded/` copy)
- [ ] 3.8 `renderer/test/inputs-endpoint.test.ts`: `'news'` → `'smart_pill'` in the inputs list

## 4. Pairing publisher rename

- [ ] 4.1 `pairing/pairing_inputs.py`: write `renderer/inputs/smart_pill.json` instead of `news.json`. If flattening, payload becomes `{"body": sp_body}` (or `{}` when absent); if preserving, keep wrapper. Update the function docstring (`prepare_renderer_inputs`)
- [ ] 4.2 `pairing/publish_today.py`: update the post-run print message at line 93 to reference `smart_pill.json`
- [ ] 4.3 Defensive insurance (optional): on each run, `unlink` the old `renderer/inputs/news.json` if present to avoid shadowing

## 5. HA documentation and breadcrumb cleanup

- [ ] 5.1 `ha/docs/architecture.md`: drop `news_sources.yaml` and `generate_news_sensors.py` lines from the directory tree; drop the `news` row from the inputs table; update the `pairing` row's "writes" path to reference `smart_pill.json` not `news.json`
- [ ] 5.2 `ha/docs/troubleshooting.md`: drop the `sensor.news_digi24` entry
- [ ] 5.3 `ha/README.md`: drop news-config mentions in the directory layout, the deploy-flow section, and the operator-editable lists paragraph
- [ ] 5.4 `ha/automations/publish_inputs.yaml`: delete the dead "Smart-pill / news previously published here…" comment block
- [ ] 5.5 `ha/integrations/rest_commands.yaml`: delete the "inkplate_publish_news removed" breadcrumb comment
- [ ] 5.6 `ha/integrations/shell_commands.yaml`: delete the "generate_curated_news removed" breadcrumb comment
- [ ] 5.7 `ha/integrations/command_line_sensors.yaml`: delete the "inkplate_curated_news sensor removed" breadcrumb comment

## 6. Tests and validation

- [ ] 6.1 `npm test --prefix renderer` passes
- [ ] 6.2 `pytest pairing/` (or whatever the pairing test entry is) passes
- [ ] 6.3 `python3 pairing/publish_today.py --dry-run` produces output that mentions `smart_pill.json`, no remaining `news.json` references
- [ ] 6.4 `grep -ri "news" renderer/src renderer/templates renderer/test pairing ha` returns only deliberate remaining occurrences (e.g., archived openspec changes — not in scope here)
- [ ] 6.5 Manual: render `/display/summary/preview` against today's pairing; smart-pill body renders with the same content and font size as before the change

## 7. Acceptance

- [ ] 7.1 The three news-infrastructure files are deleted; `git status` confirms
- [ ] 7.2 `renderer/inputs/smart_pill.json` exists; `renderer/inputs/news.json` does not
- [ ] 7.3 `grep -r "news_body\|newsInput\|requireInput('news')\|input\.news" renderer pairing ha` returns nothing
- [ ] 7.4 `ha/deploy.sh` runs cleanly without the dropped block
- [ ] 7.5 No firmware change is required and no firmware test fails
