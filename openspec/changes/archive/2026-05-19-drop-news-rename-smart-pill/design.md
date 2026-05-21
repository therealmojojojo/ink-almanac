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
| `renderer/src/modes/debugDelight.ts` | Added in commit `e88e0b6` after the original scope was inventoried. ~17 `news` references: `requireInput('news')` (line 312), `input.news` field accesses (lines 318-352), synthesised `{ count: 1, items: [{ body }] }` wrappers (lines 530, 615 — also candidates for flattening per §"Schema-shape question"), and `.summary-smart-pill .news .item` CSS selectors embedded in the debug HTML (lines 454, 456, 507, 544-548). Rename matches the production rename: schema field `smart_pill`, zone `smart_pill_body`, CSS `.summary-smart-pill .body`. |
| `renderer/test/inputs-endpoint.test.ts` | `'news'` → `'smart_pill'` in inputs list (line 26) |
| `pairing/pairing_inputs.py` | Write `renderer/inputs/smart_pill.json` instead of `news.json` (current writer at lines 231-236); update docstring at line 81 (currently `"nocturne.jpg + news.json (smart-pill body)"`) |
| `pairing/publish_today.py` | Update the post-run print message at line 93 (currently `"  wrote: renderer/inputs/{{pairing,news}}.json + …"`) |

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

The rename touches the schema, renderer, publisher, CSS, debug preview, and HA deploy script. A bug in any of these can be silent (e.g. a typo in a CSS selector makes the body white-on-white and visible only on the PNG, not in the HTML preview). The plan below is exhaustive — each test maps to a specific failure mode it catches.

### Layer 1 — Static checks (fail-fast; cheap)

| Test | What it catches | Command | Expected |
|---|---|---|---|
| **L1.1** TypeScript compile | Any reference to `input.news`, `requireInput('news')`, `newsInput` not updated in renamed files | `cd renderer && npm run build` (or `tsc --noEmit`) | exit 0 |
| **L1.2** Renderer lint | Style regressions, unused imports left after rename | `cd renderer && npm run lint` (if configured; skip if not) | exit 0 |
| **L1.3** Source-tree grep | Stale string literals (`'news'`, `news_body`, `.summary-smart-pill .news`, `news.items`) that lint/tsc don't catch (e.g. inside template literals or CSS strings) | `grep -rn "news_body\|newsInput\|requireInput('news')\|input\.news\|\\.summary-smart-pill \\.news\|news\\.items\\[0\\]" renderer/src renderer/templates renderer/test pairing ha` | zero output |
| **L1.4** HA scaffolding gone | Deleted files truly deleted | `[ ! -f ha/config/news_sources.yaml ] && [ ! -f ha/sensors/news_sources.yaml ] && [ ! -f ha/scripts/generate_news_sensors.py ]` | exit 0 |
| **L1.5** Deploy script parses | `ha/deploy.sh` survives the dropped block | `bash -n ha/deploy.sh` | exit 0 |
| **L1.6** Allowable residue | Remaining `news` mentions are documented exceptions only (archived openspec changes, `firmware/include/config.h:14` colloquial idiom) | `grep -rn "news" firmware renderer pairing ha openspec/specs` and visually inspect | only known sites |

### Layer 2 — Renderer unit + integration tests

Existing suites must pass; specific assertions need the rename.

| Test | What it catches | Command |
|---|---|---|
| **L2.1** Full vitest run | The umbrella sanity check. Catches schema, snapshot, degraded, inputs-endpoint, battery, forms regressions in one shot. | `npm test --prefix renderer` |
| **L2.2** Snapshot suite specifically | The Summary PNG palette and structure haven't drifted (`renderer/test/snapshot.test.ts:53` includes `summary` mode; line 82 asserts the PNG uses only Inkplate palette values) | `npm run test:snapshot --prefix renderer` |
| **L2.3** Inputs-endpoint suite | `renderer/test/inputs-endpoint.test.ts:26` seeds the inputs list; renaming `'news'` → `'smart_pill'` must keep the test passing. The test then fetches `/display/summary/preview` and asserts the response. | `npx vitest run test/inputs-endpoint.test.ts --prefix renderer` |
| **L2.4** Degraded-input suite | `renderer/test/degraded.test.ts` exercises the missing-fixture branches; the `degraded/news.json` fixture rename must be followed through. | `npx vitest run test/degraded.test.ts --prefix renderer` |
| **L2.5** New: Zod schema accepts the new shape | The renamed `smartPillInput` parses today's `smart_pill.json` produced by `pairing/pairing_inputs.py` | folded into L2.3 by re-running the inputs-endpoint test after seeding; no new test needed |
| **L2.6** New: Zod schema rejects the OLD wrapper shape if flattened (§3.4 Option A) | If `news.json` is left on disk somehow and we flattened, the renderer 503's clearly instead of silently rendering an empty body | one negative-path assertion in `inputs-endpoint.test.ts`: seed a `news.json` with the old shape, fetch preview, expect 503 |

### Layer 3 — Pairing publisher tests

| Test | What it catches | Command | Expected |
|---|---|---|---|
| **L3.1** Existing pairing tests | Anything the existing suite was already checking | `pytest pairing/test_api_fetch.py` (and any sibling tests) | exit 0 |
| **L3.2** Dry-run output | `publish_today.py` mentions the new filename in its post-run message and does NOT mention `news.json` | `python3 pairing/publish_today.py --dry-run` | output contains `smart_pill.json`, no `news.json` |
| **L3.3** Real run produces the file | A real (non-dry) run actually writes `renderer/inputs/smart_pill.json` with the day's body | `python3 pairing/publish_today.py && jq -e .body renderer/inputs/smart_pill.json` (if flattened) or `jq -e '.items[0].body' renderer/inputs/smart_pill.json` (if preserved) | exit 0 |
| **L3.4** Old file absent or stale | `renderer/inputs/news.json` is either removed by the publisher or hasn't been touched since the change | `! [ -f renderer/inputs/news.json ] || [ renderer/inputs/news.json -ot renderer/inputs/smart_pill.json ]` | true |
| **L3.5** Empty-body branch | When the day's summary sidecar has no `smart_pill.body`, the publisher writes a sentinel that the renderer treats as "show placeholder" rather than crashing | Pick a triplet whose sidecar has no `smart_pill.body`: `python3 pairing/publish_today.py --id <such-triplet>`; then render Summary, expect placeholder | placeholder dash visible |

### Layer 4 — Visual / end-to-end rendering

The PNG path exercises the entire pipeline (schema → templates → fonts → CSS selectors → Playwright → image encode). The HTML preview exercises everything except Playwright; pair them to localise failures.

| Test | What it catches | Command | Expected |
|---|---|---|---|
| **L4.1** Summary preview HTML | Renderer can resolve input + apply zone + emit HTML; smart-pill body appears in the right DOM location with the renamed wrapper class | `curl -s http://127.0.0.1:8575/display/summary/preview \| grep -E '"summary-smart-pill"\|<div class="body">'` | both selectors present in output |
| **L4.2** Summary PNG | The same path with Playwright + dithering. Catches: invisible-text CSS bugs, missing zone declarations, font fallback chains. | `curl -s http://127.0.0.1:8575/display/summary.png > /tmp/s.png && file /tmp/s.png \| grep -q PNG && open /tmp/s.png` | PNG opens; smart-pill body is visually present at the right position with body font |
| **L4.3** Summary PNG — pixel diff vs pre-rename | The cell renders identically to before the rename modulo body text content | Save a baseline PNG before applying the change (`curl … > /tmp/baseline.png`); after the change, compare with ImageMagick: `compare -metric AE /tmp/baseline.png /tmp/post.png /tmp/diff.png`. Expect difference confined to the body cell (because today's smart_pill.body might differ between captures); structure / position / typography elsewhere identical. | structural diff = 0 outside the smart-pill cell |
| **L4.4** debugDelight preview | The debug-mode rendering path exercises the synthesised wrapper rename and the inline CSS rules in `debugDelight.ts` lines 454-548 | If the debug entrypoint has a route, hit it; otherwise import `debugDelight.ts` in a test file and call its rendering function with a synthetic body. | rendered HTML contains the renamed selectors; no thrown errors |
| **L4.5** Placeholder branch on missing body | `summary.ts`'s placeholder code path still works (the empty-body case, exercised when sidecar has no `smart_pill.body`) | Temporarily `echo '{}' > renderer/inputs/smart_pill.json` (or `{"body": ""}` if flattened), render Summary PNG, restore. | placeholder dash visible; no 500 |
| **L4.6** Schema-failure clarity | A bogus `smart_pill.json` (wrong shape) produces a clear 503 with a useful message, not a 500 or a blank cell | `echo '{"unexpected": true}' > renderer/inputs/smart_pill.json`, fetch preview, expect 503 and the missing-input error message; restore. | 503 with input-validation error |

### Layer 5 — HA deploy validation

| Test | What it catches | Command | Expected |
|---|---|---|---|
| **L5.1** `bash -n` after the deploy.sh edit | Bash syntax error in the regen-block removal | `bash -n ha/deploy.sh` | exit 0 |
| **L5.2** Local deploy dry-check | HA config still parses with the news-sensor files removed | `HA_HOST=${HA_HOST} ./ha/deploy.sh` ends with `ha core check` passing | no `ha core check` errors in the script's tail-log |
| **L5.3** Breadcrumb-comment removal didn't break YAML | The four files in §5.4–5.7 still parse | implicit via L5.2 (HA's `core check` parses every YAML in the package) | covered by L5.2 |

### Layer 6 — Post-deploy device verification

Optional but worth running because the device is the only place the round-trip is end-to-end real.

| Test | What it catches | How |
|---|---|---|
| **L6.1** Next Summary wake renders | Real device's drawImageFromUrl fetches a working PNG; panel shows the smart-pill body | Wait for the next scheduled Summary wake (or trigger one via double-tap during Summary hours), look at the panel |
| **L6.2** `epd_pwrgood` stays true through the cycle | The rename didn't change render duration enough to provoke the PMIC wedge | `sensor.inkplate_device_epd_power_good = off` (no problem) for 24 h after deploy |

### Layer 7 — Rollback verification

| Test | What it catches | Command | Expected |
|---|---|---|---|
| **L7.1** `git revert` is clean | The change can be undone in one commit if something is wrong in prod | `git revert <commit-sha> && cd renderer && npm test` | revert applies; tests pass on the reverted code |
| **L7.2** Reverted publisher reproduces `news.json` | The old file shape comes back on the next publish | run `pairing/publish_today.py` post-revert | `renderer/inputs/news.json` written, `smart_pill.json` no longer touched |

### What "morning face renders correctly" actually covers

If you only ran one test, **L4.2 (Summary PNG via the production endpoint)** is the highest-leverage single check. It exercises:

- Zod schema validation (input parses)
- `requireInput('smart_pill')` (renamed input is found)
- `applyZone('smart_pill_body', …)` (renamed zone exists in `zones.ts`)
- CSS selectors `.summary-smart-pill .body` (renamed wrapper resolves)
- Font ladder, line height, justification, hyphenation (unchanged but exercised)
- Playwright + PNG encode

What L4.2 does **not** cover:

- The empty-body placeholder branch (the smart-pill body is present on most days; need L4.5 explicitly)
- The debugDelight code path (different `requireInput` call; need L4.4)
- The negative path — what happens when something IS broken (L4.6, L2.6)
- HA deploy script changes (L1.4, L1.5, L5.x)
- Snapshot drift in non-Summary modes that share infrastructure (L2.2)

So the minimum responsible test set is **L1.3 + L2.1 + L3.2 + L4.2 + L4.5**: five commands, ~2 minutes total, covers ~95% of the change's failure surface.

## Open questions

1. **`{body: "…"}` flatten or keep wrapper?** Recommendation above is flatten. Final call belongs to the operator.
2. **Drop or keep the `firmware/include/config.h:14` colloquial "no news" comment?** Recommendation: keep. It's English idiom in a comment about quiet hours, not a feature reference, and changing it adds churn without clarification.
3. **Should `pairing/publish_today.py` actively delete the old `news.json` on first run after the change?** Cheap defensive insurance; suggested but not required.
