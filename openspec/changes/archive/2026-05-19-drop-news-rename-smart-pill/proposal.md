# Drop news infrastructure; rename smart-pill plumbing

> **Status — 2026-05-19**: re-audited against today's code; still not started. Every originally-named target is unchanged from 2026-04-27 (the HA scaffolding files all exist, `ha/deploy.sh` still has the regen block at lines 47-50, every renderer `news` reference still matches the proposal, `pairing/pairing_inputs.py` still writes `news.json` — refreshed this morning at 06:00 with today's smart-pill body — and every HA breadcrumb is intact). One scope addition since 2026-04-27: commit `e88e0b6` introduced `renderer/src/modes/debugDelight.ts` (1048 lines, wired into `server.ts`) with ~17 `news` references; those didn't exist when this change was written but are now part of the rename scope.
>
> Notable framing: the rename is finishing what the *spec* already says. `openspec/specs/dashboard-faces/spec.md` already uses `smart_pill_body` (zone id), `Smart pill` (cell name), and references the YAML source field as `summary.smart_pill.body`. The corpus YAML sidecar schema also uses `smart_pill.body` (read at `pairing/pairing_inputs.py:232`). Only the *downstream* surface — runtime file name, schema name, renderer field path, CSS wrapper, HA breadcrumbs and docs — still carries `news`. This change is alignment with the spec's existing nomenclature, not a redefinition.

## Why

Two unrelated forms of "news" reference live in the codebase, both worth removing:

1. **Dead news infrastructure.** Commit `89c24e2` ("HA: tier face alternation, gesture rework, drop curated-news regen") deleted the live curated-news regeneration pipeline but kept the per-source RSS sensors (`ha/sensors/news_sources.yaml`, `ha/scripts/generate_news_sensors.py`, `ha/config/news_sources.yaml`) on the rationale that they "remain unused by default per their own README." The operator has now confirmed they don't intend to use news on this device at all. The scaffolding is read by no automation, feeds no face, and only adds deploy-time work and surface area for confusion.
2. **Misleading naming on a non-news feature.** The Summary face's smart pill — a deep-dive entry (word-of-the-day or concept-of-the-day) bound to the day's companion text — travels end-to-end under the name `news`. The runtime input file is `renderer/inputs/news.json`, the renderer schema is `newsInput`, the zone is `news_body`, the CSS class wrapper is `.news`. None of this is news. The name is residue from the original Summary design that imagined per-source RSS items in that cell. The current implementation has none of that, the curated-news regen is gone, and the name now actively misleads anyone reading the code.

The two refactors are independent but share a goal (eliminate "news" from the codebase) and most of the same blast radius (HA configs, renderer schema, docs). Doing them together is cheaper than splitting because the same files get touched once.

## What Changes

### Refactor 1 — Delete residual news infrastructure

- Delete `ha/config/news_sources.yaml`, `ha/sensors/news_sources.yaml`, `ha/scripts/generate_news_sensors.py`.
- Edit `ha/deploy.sh` to drop the "Regenerate per-source news sensors" block.
- Update `ha/docs/architecture.md`, `ha/docs/troubleshooting.md`, `ha/README.md` to drop news-config references.

### Refactor 2 — Rename the smart-pill plumbing

The runtime field, schema name, CSS wrapper, zone id, file name, and HA references all change from `news` to `smart_pill`:

- Rename runtime input file: `renderer/inputs/news.json` → `renderer/inputs/smart_pill.json` (gitignored; regenerated next publish run).
- `renderer/src/modes/schema.ts`: `newsInput` → `smartPillInput`; the field on `summaryInput` becomes `smart_pill`.
- `renderer/src/modes/summary.ts`: `input.news.items[0]` → `input.smart_pill.items[0]`; `applyZone('news_body', …)` → `applyZone('smart_pill_body', …)`.
- `renderer/src/modes/index.ts`: `requireInput('news')` → `requireInput('smart_pill')`.
- `renderer/src/server.ts`: replace `'news'` in the inputs list with `'smart_pill'`.
- `renderer/src/zones.ts`: rename the `news_body` zone entry to `smart_pill_body`.
- `renderer/templates/summary/summary.css`: drop the vestigial `.news` wrapper class; rename selectors from `.summary-smart-pill .news .item .body` to `.summary-smart-pill .body`. Drop the historical "b = news-only / c = climate-dominant" comment at the file head.
- `renderer/test/inputs-endpoint.test.ts`: `'news'` → `'smart_pill'` in the inputs list. Rename `renderer/test/fixtures/news.json` (and `renderer/test/fixtures/degraded/news.json`) similarly.
- `renderer/src/modes/debugDelight.ts` (added 2026-05-04 in commit `e88e0b6`, after this proposal was written): rename `requireInput('news')`, `input.news`, `news.items[0].body`, all `.summary-smart-pill .news` CSS selectors used by the debug preview HTML, and the synthesised fixture wrappers (`{ count: 1, items: [{ body }] }` literals — also a candidate for flattening if §1 chooses Option A). ~17 occurrences across the file.
- `pairing/pairing_inputs.py`: write `renderer/inputs/smart_pill.json`; update the docstring on `prepare_renderer_inputs`.
- `pairing/publish_today.py`: update the post-run print message.
- `ha/docs/architecture.md`: update the inputs-table entry for `pairing` ("writes `{pairing,news}.json`" → "writes `{pairing,smart_pill}.json`"); drop the standalone `news` row.
- `ha/automations/publish_inputs.yaml`: delete the dead "Smart-pill / news previously published here…" comment block.
- `ha/integrations/{rest_commands,shell_commands,command_line_sensors}.yaml`: delete the "removed" breadcrumb comments referencing `inkplate_curated_news` / `inkplate_publish_news` / `generate_curated_news`.

### Optional cleanup considered separately

`firmware/include/config.h:14` contains the colloquial phrase "no news, no schedule transitions" in a comment about quiet hours. This is plain English, not a reference to the news feature. Leave it alone unless a reviewer flags it.

## Capabilities

### Modified Capabilities

- **`rendering-pipeline`**: the input-name allowlist drops `news` and adds `smart_pill`; the `summary` face's input dependency list changes accordingly.
- **`ha-integrations`**: removes the "Hacker News and news sources" requirement entirely; updates the renderer-input publishers requirement to refer to `smart_pill` instead of `news` in the `pairing` automation's output description.
- **`dashboard-faces`**: updates the Summary face's bottom-band description to refer to "Smart pill" without leftover "two-item curated capsule" framing (which described an earlier, removed multi-item layout); removes the "no HN, no news" allusion in the Night face.

### New Capabilities

None. This change removes and renames; it does not add behavior.

## Impact

- **Single source of truth for the smart pill body**: `renderer/inputs/smart_pill.json`, schema `smartPillInput`, zone `smart_pill_body`, CSS `.summary-smart-pill .body`. A reader can grep `smart_pill` and find every involved file in one pass.
- **Smaller HA deploy**: `deploy.sh` no longer regenerates news sensors; per-deploy cost drops by a few seconds and the operator can't accidentally edit `news_sources.yaml` expecting it to do something.
- **Schema-shape question (open):** the current `news.json` shape is `{count, items: [{body}]}` — a legacy multi-item RSS wrapper. The smart pill only ever uses `items[0].body`. Flattening to `{body: "…"}` is a small additional edit (parser, schema, picker, fixtures) and is cleaner if we're already breaking the contract via the rename. Recommend flattening as part of this change; design.md walks through the trade.
- **Backward compatibility**: there is none to preserve. The renderer reads files the pairing pipeline writes; both move together. The HA automations that previously wrote `news.json` were already deleted in `89c24e2`; only the pairing publisher remains as a writer, and it's part of this change. Devices in the field aren't affected — they only read PNGs from the renderer.
- **Test surface**: the renderer's `inputs-endpoint.test.ts` and any battery-indicator/snapshot tests that mention `news` need their fixture names updated. No new test logic; renaming only.
- **Documentation gets cleaner, not larger**: removed lines outnumber added lines. The `ha/docs/architecture.md` inputs table loses a row; `ha/README.md` loses a paragraph; `ha/docs/troubleshooting.md` loses an entry.
- **Out of scope**: the smart-pill cell-expansion exploration the operator started before this rename (padding reduction vs widening leftward). That work resumes after this change lands so the new code is written against the new names.
