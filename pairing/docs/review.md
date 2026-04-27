# Triplet review (`corpus review`)

Web-based per-triplet review tool. Walks every triplet in
`corpus/_triplets/`, renders Summary / Weather / Gallery / Night faces
through the local renderer, and captures a verdict per triplet directly
into the YAML sidecar.

## Why it exists

Authoring a corpus item is one judgement call: "is this poet, this
poem, this image worth the panel?" Authoring a *triplet* — the
anchor + summary + gallery group that anchors a single day on the
device — is a different judgement: "do these three pieces play
together when the operator stares at them at 8am?" The faces themselves
add another layer: the same triplet can read as intentional in
gallery-visual landscape and disjointed in gallery-text. Reviewing in
the rendered context catches that.

The tool replaces the would-be PDF-based viability review (see
`openspec/changes/archive/2026-04-27-experiment-pairing-viability/` for
the original design): per-triplet, in-browser, with the renderer in
the loop, so the review judges the actual displayed pixels and not a
flattened PDF approximation.

## How it works

```
$ cd renderer && npm run dev          # in one terminal — needs the renderer up
$ corpus review                       # in another — defaults to port 8081
# open http://localhost:8081
```

Each triplet is staged into the renderer (writes
`renderer/inputs/pairing.json`, `companion.jpg`, `gallery.jpg`,
`nocturne.jpg` per item) before the preview iframe loads, so the
preview shows exactly what the device would draw on its next Full.

For each triplet you choose:

- **Keep** — sets `triplet_verdict: keep`, optional comment.
- **Reject content** — `triplet_verdict: reject-content`, e.g. summary
  doesn't pull its weight, anchor too on-the-nose, gallery too literal.
- **Reject layout** — `triplet_verdict: reject-layout`, e.g. gallery
  image looks bad in split-portrait orientation, or the title wraps
  awkwardly.
- **Skip** — clears any prior verdict (returns the triplet to
  unreviewed state).

The verdict is written back to the triplet sidecar:

```yaml
triplet_verdict: keep
triplet_verdict_reason: 'Marcus and Munch — anxiety as fact of waking.'
triplet_verdict_reviewed_at: '2026-04-23'
```

Subsequent runs of the daily picker (`pairing/publish_today.py`) don't
filter on `triplet_verdict` today — the rotation walks the full pool by
sequence regardless. The verdicts are advisory; if you want to drop a
rejected triplet from rotation, delete its YAML or move it under a
`corpus/_triplets/_rejected/` subdirectory.

## CLI flags

```sh
corpus review [--port N] [--renderer URL] [--only-unreviewed] [--start <triplet-id>]
```

| Flag | Default | Effect |
|---|---|---|
| `--port` | 8081 | port for the review HTTP server |
| `--renderer` | `http://localhost:8575` (or `$RENDERER_URL`) | renderer base URL the previews hit |
| `--only-unreviewed` | off | filters to triplets with no `triplet_verdict` set; useful for incremental review across sessions |
| `--start <id>` | first triplet | jump to a specific triplet (basename of `corpus/_triplets/<id>.yaml`) |

## What the UI shows

For each triplet, the iframe loads the live renderer's
`/display/<face>/preview` for Summary, Weather, Gallery, Night — same
HTML the PNG render flow uses, just without the screenshot pass. You
see exactly what the operator would see at 8am.

A small toolbar at the top shows triplet ID, sequence, and current
verdict (if any). Keyboard shortcuts:

- `Enter` / `K` → keep
- `C` → reject-content
- `L` → reject-layout
- `S` → skip / clear
- `→` → next, `←` → previous

## Side effect on `renderer/inputs/`

Every navigation overwrites `renderer/inputs/pairing.json` (and the
companion / gallery / nocturne binaries) with the currently-staged
triplet — *that's how* the preview renders. This means **while a
review session is open, the live device's renderer is also serving the
review's currently-staged triplet**, not today's actual triplet.

If you forget and leave a review session running, the device will
eventually wake on its 15-min Full cadence, fetch the renderer, and
display whatever triplet was last staged. To restore today's pairing
after a review:

```sh
python3 pairing/publish_today.py
```

(That's how we discovered the issue: the smart pill swapped to a
different summary item mid-day. The session was open in another tab.)

## Optional: device simulator (`/sim`)

The tool also includes a `/sim` view that exercises the HA-side
automations (alternation tick, gesture handler, override state machine)
against a clock you can pin to any minute of the day. Useful for
testing a schedule change end-to-end without waiting 15 minutes per
boundary.

Requires `ha/secrets.yaml` to be present locally with a valid
`ha_long_lived_token` — the simulator talks to HA's REST API for
state-sets and reads MQTT-published `active_mode` to decide what to
render.

The `/sim` view is not for end users; it's for the developer iterating
on automations. If `ha_long_lived_token` is missing the route returns
a helpful error.

## When to run a review session

- After a corpus harvest commit (`corpus harvest --commit <batch>`) —
  the new items will be paired into triplets by the next
  `build_triplets.py` run, and those new triplets need first-pass
  review.
- After substantial tag taxonomy edits — pairings whose match was
  driven by a renamed/dropped tag may now read differently.
- Whenever you suspect rotation is showing a triplet that doesn't
  belong (open the tool with `--start <triplet-id>` and use the
  reject-content / reject-layout flags to flag it for later cleanup).

## Related

- [`pairing/README.md`](../README.md) — CLI reference + install
- [`pairing/docs/triplet-generation.md`](triplet-generation.md) — how
  triplets are generated upstream of review.
- [`pairing/docs/ingestion-workflow.md`](ingestion-workflow.md) — how
  corpus items get into the pool that triplets are built from.
- [`HOWTO.md` § Override today's triplet](../../HOWTO.md#override-todays-triplet)
  — the reverse operation: pick a specific triplet to display today.
