# Design — Drop news, rename smart-pill plumbing

## Goal

Eliminate every reference to "news" from the codebase. Two concrete shapes:

1. **Delete** the dead RSS news scaffolding (config, generator, sensors, deploy hook, docs).
2. **Rename** the smart-pill plumbing from `news` to `smart_pill` end-to-end (file name, schema name, zone id, CSS wrapper class, pairing publisher field, HA docs).

After the change, `grep -ri news .` should return zero hits in source paths (the colloquial use of the word in `firmware/include/config.h:14` is the only deliberate exception, and it's a generic English idiom unrelated to the news feature).

## Non-goals

- Behavioral changes to the smart pill itself (font ladder, cell geometry, body length budget). Those are the operator's open question and live in a separate exploration once this rename lands.
- Restructuring the Summary face beyond the smart-pill section.
- Removing the `firmware/include/config.h:14` colloquial mention. Comment is plain English ("nothing happens"); changing it is more disruptive than leaving it.
- Migrating older devices' state. The renamed files are renderer-side; devices read PNGs only.

## Scope inventory

### Files to delete

| File | Reason |
| --- | --- |
| `ha/config/news_sources.yaml` | RSS source declarations; no automation reads them |
| `ha/sensors/news_sources.yaml` | Auto-generated from above; consumed by no face |
| `ha/scripts/generate_news_sensors.py` | Regenerator for the sensors file |

### Files to edit (rename references)

| File | What changes |
| --- | --- |
| `ha/deploy.sh` | Drop the "Regenerate per-source news sensors" block (~5 lines) |
| `ha/docs/architecture.md` | Drop `news_sources.yaml` and `generate_news_sensors.py` lines from the directory tree; drop the `news` row from the inputs table; update the `pairing` row's "writes" path |
| `ha/docs/troubleshooting.md` | Drop the `sensor.news_digi24` entry |
| `ha/README.md` | Drop news-config mentions in the directory layout, the deploy-flow section, and the operator-editable lists paragraph |
| `ha/automations/publish_inputs.yaml` | Delete the dead "Smart-pill / news previously published here…" comment block |
| `ha/integrations/rest_commands.yaml` | Delete the "inkplate_publish_news removed" comment |
| `ha/integrations/shell_commands.yaml` | Delete the "generate_curated_news removed" comment |
| `ha/integrations/command_line_sensors.yaml` | Delete the "inkplate_curated_news sensor removed" comment |
| `renderer/src/modes/schema.ts` | `newsInput` → `smartPillInput`; field on `summaryInput` `news` → `smart_pill` |
| `renderer/src/modes/summary.ts` | `input.news.items[0]` → `input.smart_pill.items[0]`; `applyZone('news_body', …)` → `applyZone('smart_pill_body', …)` |
| `renderer/src/modes/index.ts` | `requireInput('news')` → `requireInput('smart_pill')` |
| `renderer/src/server.ts` | `'news'` → `'smart_pill'` in inputs allowlist |
| `renderer/src/zones.ts` | `news_body` zone entry → `smart_pill_body` |
| `renderer/templates/summary/summary.css` | Drop `.news` wrapper class; selectors become `.summary-smart-pill .body`; drop the `b = news-only / c = climate-dominant` historical comment at file head |
| `renderer/test/inputs-endpoint.test.ts` | `'news'` → `'smart_pill'` in inputs list |
| `pairing/pairing_inputs.py` | Write `renderer/inputs/smart_pill.json` instead of `news.json`; update docstring |
| `pairing/publish_today.py` | Update the post-run print message |

### Runtime artifact rename

`renderer/inputs/news.json` → `renderer/inputs/smart_pill.json` (gitignored; recreated on next `pairing/publish_today.py` run).

### Test fixtures

`renderer/test/fixtures/news.json` (and any `degraded/news.json`) → `smart_pill.json`. All fixture-using tests pick up the new name automatically once the schema enforces it.

## Schema-shape question — flatten or preserve?

Current shape (`renderer/inputs/news.json`):

```json
{
  "count": 1,
  "items": [
    { "body": "…" }
  ]
}
```

Smart-pill code only ever reads `items[0].body`. The wrapper is residue from the original "RSS feed with N items" design, dead since the curated-news regen was removed in `89c24e2`.

**Option A — Flatten to `{body: "…"}`.** Cleaner schema, smaller file, less code in the picker. Schema becomes:

```ts
export const smartPillInput = z.object({
  body: z.string(),
});
```

And `summary.ts` becomes `const safe = applyZone('smart_pill_body', input.smart_pill.body);` — one indexing layer removed.

**Option B — Preserve `{count, items: [{body}]}`.** Smaller diff. No need to rewrite the picker's first-item check or the placeholder branch (`if (!first) {…}`). But the wrapper has no future use we can foresee.

**Recommendation: flatten (Option A).** The rename is already breaking the on-disk contract; flattening it at the same time costs ~10 extra lines of edit and removes a stale data shape. The placeholder branch becomes simpler too (`if (!input.smart_pill?.body)` instead of the items[0] guard).

If the picker ever needs multiple smart-pill items in the future (the bound-companion design we currently have makes this unlikely), the schema can be extended back. But YAGNI: flatten now, expand later if ever needed.

## Migration / sequencing

The change is a single deploy. There is no in-flight version to bridge:

1. Edit the source files (renderer + pairing) in lockstep.
2. Delete the HA scaffolding files; edit `deploy.sh` and docs.
3. Run `pairing/publish_today.py` — produces `smart_pill.json`.
4. Run the renderer (`npm test`, then a manual `/display/summary/preview` check against today's pairing).
5. `rm renderer/inputs/news.json` once the new file is confirmed in place.
6. Deploy HA; the `deploy.sh` change goes out the same time as the renderer change.

No firmware change. The device reads PNGs only; it doesn't see input file names.

## Risks and edge cases

| Risk | Mitigation |
| --- | --- |
| Operator forgets to regenerate `smart_pill.json` after pulling the change | The renderer's `requireInput('smart_pill')` returns 503 with a clear "missing input" message; the operator's next `publish_today.py` run fixes it. Document in the change log. |
| Stale `news.json` left on disk shadows the rename | `pairing/publish_today.py` could optionally `unlink` an old `news.json` if present. Cheap defensive insurance; suggested as a one-shot in tasks. |
| External tooling (gitignored scripts, dev environments) hardcodes `news.json` | The repo is operator-only; no external consumers. Document the rename in `HOWTO.md` if it has a relevant section. |
| HA automation YAML accidentally still references `inkplate_curated_news` | Delete the breadcrumb comments in this change so future grep returns nothing. |

## Test plan

- `renderer/test/inputs-endpoint.test.ts`: existing assertions still pass after fixture rename.
- `renderer/test/battery-indicator.test.ts`: no smart-pill assertions; should be untouched.
- Add: `renderer/test/smart-pill.test.ts` (small) verifying `summary` preview HTML contains the body string from `smart_pill.json` and the picker's font-size class is applied. (Optional; could fold into `inputs-endpoint.test.ts` instead.)
- Manual: `/display/summary/preview` against today's pairing renders identically pre- and post-rename, modulo zero behavioral change.

## Open questions

1. **`{body: "…"}` flatten or keep wrapper?** Recommendation above is flatten. Final call belongs to the operator.
2. **Drop or keep the `firmware/include/config.h:14` colloquial "no news" comment?** Recommendation: keep. It's English idiom in a comment about quiet hours, not a feature reference, and changing it adds churn without clarification.
3. **Should `pairing/publish_today.py` actively delete the old `news.json` on first run after the change?** Cheap defensive insurance; suggested but not required.
