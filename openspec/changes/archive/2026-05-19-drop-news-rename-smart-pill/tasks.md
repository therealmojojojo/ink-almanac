# Tasks — Drop news, rename smart-pill plumbing

> **Status — 2026-05-19**: re-audited; 0 of 41+ tasks complete. Original task list is intact (nothing has been done since 2026-04-27). One new task block added (§3.9) for `renderer/src/modes/debugDelight.ts`, which appeared after the original inventory.

## 1. Resolve the schema-shape question

- [ ] 1.1 Operator decides: flatten `news.json` to `{body: "…"}` (recommended) or preserve the `{count, items: [{body}]}` wrapper. Tasks below assume flatten; revise §3.1, §3.9, and §4.1 if the operator chooses preserve.

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
- [ ] 3.7 Rename test fixtures: `renderer/test/fixtures/news.json` → `smart_pill.json` (and any `degraded/` copy — both confirmed present 2026-05-19)
- [ ] 3.8 `renderer/test/inputs-endpoint.test.ts`: `'news'` → `'smart_pill'` in the inputs list (line 26)
- [ ] 3.9 `renderer/src/modes/debugDelight.ts` (added 2026-05-04 in commit `e88e0b6`; not in the original inventory): rename every `news` reference end-to-end. Concrete sites:
  - line 312: `requireInput('news')` → `requireInput('smart_pill')`
  - lines 318, 352: `news` destructure + return field
  - lines 454-548: `.summary-smart-pill .news .item` CSS selectors embedded in the debug HTML output strings → `.summary-smart-pill` selectors that match the production rename (§3.6)
  - lines 530, 615: synthesised wrappers `{ count: 1, items: [{ body }] }` → flattened `{ body }` if §1.1 chose flatten, else preserved wrapper with renamed field
  - All comment-text mentions of "news" referring to the cell (lines 9, 308, 454, 456, 507, 511, 528, 529)
  Test: `npm test --prefix renderer` still passes; manual `/display/debug-delight/preview` (or whatever the debug route is) renders identically.

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

Mirrors the layered plan in `design.md` § "Test plan". Each task lists the exact command and the expected outcome. Layers must be run in order — Layer 1 fail-fast catches almost every typo before paying for Playwright snapshot regeneration.

### 6.A Layer 1 — Static checks

- [ ] 6.A.1 **L1.1** TypeScript compiles: `cd renderer && npm run build` exits 0
- [ ] 6.A.2 **L1.2** Lint clean (if configured): `cd renderer && npm run lint`
- [ ] 6.A.3 **L1.3** No stale string literals: `grep -rn "news_body\|newsInput\|requireInput('news')\|input\.news\|\.summary-smart-pill \.news\|news\.items\[0\]" renderer/src renderer/templates renderer/test pairing ha` returns nothing
- [ ] 6.A.4 **L1.4** HA scaffolding deletions confirmed: `! [ -f ha/config/news_sources.yaml ] && ! [ -f ha/sensors/news_sources.yaml ] && ! [ -f ha/scripts/generate_news_sensors.py ]`
- [ ] 6.A.5 **L1.5** `bash -n ha/deploy.sh` exits 0
- [ ] 6.A.6 **L1.6** Remaining `news` mentions in `grep -rn "news" firmware renderer pairing ha openspec/specs` are only documented exceptions (archived openspec changes; `firmware/include/config.h:14` colloquial idiom)

### 6.B Layer 2 — Renderer unit + integration

- [ ] 6.B.1 **L2.1** Full vitest suite: `npm test --prefix renderer` passes
- [ ] 6.B.2 **L2.2** Snapshot suite specifically: `npm run test:snapshot --prefix renderer` passes (will need snapshot regeneration once intentionally — review the diff to confirm only smart-pill DOM rename, no pixel drift)
- [ ] 6.B.3 **L2.3** Inputs-endpoint suite: `npx vitest run test/inputs-endpoint.test.ts --prefix renderer` passes; `'news'` → `'smart_pill'` change at line 26 is the seeded input
- [ ] 6.B.4 **L2.4** Degraded-input suite: `npx vitest run test/degraded.test.ts --prefix renderer` passes; the `degraded/news.json` fixture has been renamed
- [ ] 6.B.5 **L2.6** Negative-shape test (if §1.1 flattens): add an assertion in `inputs-endpoint.test.ts` that seeding a stale `{count, items: [{body}]}` shape produces a clear 503, not a silent empty render

### 6.C Layer 3 — Pairing publisher

- [ ] 6.C.1 **L3.1** Existing pairing tests pass: `pytest pairing/test_api_fetch.py` (plus any siblings)
- [ ] 6.C.2 **L3.2** Dry-run mentions new file: `python3 pairing/publish_today.py --dry-run 2>&1 | grep -q smart_pill.json` AND `! grep -q "news.json" <(python3 pairing/publish_today.py --dry-run 2>&1)`
- [ ] 6.C.3 **L3.3** Real run produces correct shape: `python3 pairing/publish_today.py && jq -e '<.body if flat else .items[0].body>' renderer/inputs/smart_pill.json`
- [ ] 6.C.4 **L3.4** Old runtime file is absent or stale: `! [ -f renderer/inputs/news.json ] || [ renderer/inputs/news.json -ot renderer/inputs/smart_pill.json ]`
- [ ] 6.C.5 **L3.5** Empty-body branch: pick a triplet whose sidecar omits `smart_pill.body`; run `publish_today.py --id <such-triplet>`; confirm placeholder renders (covered by 6.D.5)

### 6.D Layer 4 — Visual / end-to-end

- [ ] 6.D.1 **L4.1** Summary preview HTML contains both `class="summary-smart-pill"` and the renamed body wrapper: `curl -s http://127.0.0.1:8575/display/summary/preview | grep -E 'summary-smart-pill' | grep -E '<div class="body">'`
- [ ] 6.D.2 **L4.2** Summary PNG renders (the "morning face test"): `curl -s http://127.0.0.1:8575/display/summary.png > /tmp/s.png && file /tmp/s.png | grep -q PNG && open /tmp/s.png` — visually confirm the smart-pill body is in the right cell at the right font size
- [ ] 6.D.3 **L4.3** Pre/post pixel diff: save a `/tmp/baseline.png` before applying the rename; after the change, `compare -metric AE /tmp/baseline.png /tmp/post.png /tmp/diff.png` shows differences confined to the smart-pill body cell (text content) — typography, position, all other cells identical
- [ ] 6.D.4 **L4.4** debugDelight preview: hit the debug entrypoint (or test directly via a vitest case importing `debugDelight.ts`); rendered HTML contains the renamed selectors and the synthesised body
- [ ] 6.D.5 **L4.5** Placeholder branch: `mv renderer/inputs/smart_pill.json /tmp/sp.bak && echo '{}' > renderer/inputs/smart_pill.json && curl -s http://127.0.0.1:8575/display/summary.png > /tmp/s-empty.png && open /tmp/s-empty.png && mv /tmp/sp.bak renderer/inputs/smart_pill.json` — confirm placeholder dash, no 500
- [ ] 6.D.6 **L4.6** Schema-failure clarity: `echo '{"unexpected": true}' > renderer/inputs/smart_pill.json && curl -i http://127.0.0.1:8575/display/summary/preview` returns 503 with a useful input-validation error; restore the file afterwards

### 6.E Layer 5 — HA deploy

- [ ] 6.E.1 **L5.1** `bash -n ha/deploy.sh` exits 0 (same as 6.A.5; kept here for the layered grouping)
- [ ] 6.E.2 **L5.2** Run the real deploy: `HA_HOST=192.168.1.212 ./ha/deploy.sh` ends with the "Validating config + restarting HA core" block exiting 0 — covers L5.3 implicitly (HA's `core check` parses every YAML in the package)

### 6.F Layer 6 — Post-deploy device verification

- [ ] 6.F.1 **L6.1** Next Summary wake on the device renders correctly: watch the panel during a Summary hour or trigger a tap-to-Summary; smart-pill body visible
- [ ] 6.F.2 **L6.2** Across the 24 h after deploy, `binary_sensor.inkplate_device_epd_power_good` stays `off` (no problem) — confirms the rename didn't change render duration enough to provoke a PMIC wedge

### 6.G Layer 7 — Rollback drill

- [ ] 6.G.1 **L7.1** `git revert <commit-sha> -n && npm test --prefix renderer` exits 0 (confirms a clean rollback path before committing the rename in the first place; abandon the revert with `git reset --hard HEAD` after)
- [ ] 6.G.2 **L7.2** Post-revert: `python3 pairing/publish_today.py` reproduces `renderer/inputs/news.json` and no longer writes `smart_pill.json`

### Minimum responsible test set

If time-pressed, the smallest set that covers ~95% of the change's failure surface: **6.A.3 + 6.B.1 + 6.C.2 + 6.D.2 + 6.D.5** — five commands, ~2 minutes. Skip at your own risk.

## 7. Acceptance

- [ ] 7.1 The three news-infrastructure files are deleted; `git status` confirms
- [ ] 7.2 `renderer/inputs/smart_pill.json` exists; `renderer/inputs/news.json` does not
- [ ] 7.3 `grep -r "news_body\|newsInput\|requireInput('news')\|input\.news\|\.summary-smart-pill \.news" renderer pairing ha` returns nothing (the extra `.summary-smart-pill .news` pattern catches the debugDelight.ts embedded CSS rule)
- [ ] 7.4 `ha/deploy.sh` runs cleanly without the dropped block
- [ ] 7.5 No firmware change is required and no firmware test fails
