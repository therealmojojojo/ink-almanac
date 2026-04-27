# Change archive

Archived OpenSpec changes — design proposals + tasks lists for work that has
shipped (or been superseded). Each subdirectory is named
`YYYY-MM-DD-<change-id>/` after the date the change was archived (NOT when it
was originally proposed).

## Why archives matter

OpenSpec's source-of-truth model puts ratified capabilities in
[`openspec/specs/`](../../specs/) (clean, current). Active proposals live in
[`openspec/changes/`](..) (drafty, in-flight). Once a change has shipped and
its spec deltas have been merged into `specs/`, the change directory itself
moves here as a historical record:

- Why the work was done at all (`proposal.md`).
- What design decisions were considered and rejected (`design.md`).
- The task plan and what was actually checked off (`tasks.md`).

If you want to know *what the system does today*, read `openspec/specs/` and
the source code. If you want to know *why it does that*, the rationale is
often in one of the archived proposals.

## Index

### 2026-04-27 — partial-refresh clock + alternation engine + tap rework

The big batch: a wave of architecturally-significant changes shipped together
during April 2026, archived after end-to-end validation on the operator's
working install.

| Change | Spec(s) created/modified | Notes |
|---|---|---|
| `add-dashboard-faces` | dashboard-faces | Six faces: Summary, Weather, Gallery (visual + text), Night, Now-Playing. Layouts, zones, graceful-degradation. |
| `add-device-firmware` | device-firmware, device-wake-protocol | The device's tick orchestrator, wake/sleep strategy, MQTT contracts, battery reporting. |
| `add-device-simulation` | device-simulation | Host simulator + mock HAL + scenario harness. |
| `add-ha-integrations` | (skipped specs — already covered) | HA automations, sensors, scripts, integrations. |
| `add-ha-renderer-input-bridge` | dashboard-faces, ha-integrations, rendering-pipeline | `POST /inputs/:name` publisher pattern (HA → renderer). |
| `add-local-clock-tick` | (modified rendering-pipeline) | The 1-bit partial-refresh clock zone, baked Fraunces glyphs, post-Full cleanup. |
| `add-now-playing-mode` | now-playing-override | Sonos integration, album-art rendering, override state machine. |
| `add-owm-minutely-nowcast` | (skipped specs — operator config) | OpenWeather minutely-precip nowcast wiring. |
| `add-rendering-pipeline` | rendering-pipeline, typography-routing | Node + Playwright + sharp pipeline; CSS templates per face. |
| `improve-text-crispness` | (modified rendering-pipeline) | Hardware-validated dither policy: greyscale-only on server, device does Floyd-Steinberg. |
| `move-pir-to-ha-motion` | (skipped specs — already covered) | On-device PIR removed; motion now arrives as `HACommand` wake. |
| `revise-tap-override-semantics` | (skipped specs — superseded by alternation engine) | Tap-override precedence: explicit beats ambient. Now superseded by the unified-tap design (single == double, flips alternation phase) but retained for the precedence model. |

### 2026-04-19 — face-density + zone-fit requirements

Five small spec increments tightening the dashboard-faces contract on
content fit, gallery hero density, and orientation handling.

### 2026-04-18 — corpus + seed work

The original corpus schema + seed-corpus + earliest ingestion work.
`add-corpus-ingestion` was later split / superseded by `add-ingestion-automation`
(still in-flight under `openspec/changes/`).

## How a change ends up here

1. The work ships. Tasks are checked or marked N/A.
2. `openspec validate <change>` passes.
3. `openspec archive <change>` runs:
   - Merges the spec deltas (`changes/<name>/specs/...`) into `openspec/specs/`.
   - Moves the change directory here with the date prefix.
4. The clean spec at `openspec/specs/<capability>/spec.md` is the new source of truth.

If validation can't pass for structural reasons (e.g. duplicate requirement
from a prior archive, deltas in the wrong format), use
`openspec archive <name> --skip-specs --no-validate -y` to archive *just* the
proposal/design/tasks files and leave the spec untouched — the spec was
already updated by an earlier archive's merge. The archive markers in this
README track which changes used `--skip-specs`.
