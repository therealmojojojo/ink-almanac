## Context

`ha/docs/architecture.md` advertises a data flow where "HA produces, renderer consumes." In practice, only the Sonos and pairings paths have writers. Every other input is served from 2-day-old fixtures that happen to live at the same paths. The fact that the rendered simulation looks mostly plausible has masked the absence of the bridge.

Two adjacent facts motivate the bundled scope:

1. The battery indicator misplacement (`climate.inside.battery`, honored only by Summary) surfaced in the same investigation. Fixing it in isolation would require re-seeding four goldens without a live writer — effectively testing against a hand-edited fixture. Doing it together with the publisher lets the new fixture shape and the live writer land together.
2. The writer mechanism (endpoint vs. SSH-script) is a one-time choice that should be consistent for all five writers. Choosing per-input would leave future-us guessing which path is canonical.

## Goals / Non-Goals

**Goals:**

- Close the HA→renderer bridge for all five missing inputs in one change.
- Make the battery indicator accurate on all five faces.
- Keep the renderer stateless — writes hit disk, reads remain file-based.
- Authentication sufficient for the LAN threat model (not internet-facing).

**Non-Goals:**

- Re-architect the renderer to pull from HA via HTTP. Push-to-file is simpler, aligns with how Sonos already works (a script writes `sonos.json`), and decouples render-time from HA availability.
- Change the HA→device MQTT contract. That path is orthogonal to the HA→renderer bridge.
- Ship the kitchen climate sensor. That sensor is still deferred (§4 of `add-ha-integrations`); when it arrives, its writer is a single additional HA automation, not a spec change.
- Build a dashboard-wide state reconciler. Each input is independently refreshed; stale inputs are a diagnostic concern, not a runtime correctness concern.

## Decisions

### Writer mechanism: `POST /inputs/:name` over LAN, not SSH-script

Two options were considered:

1. **SSH + shell script, per Sonos.** HA invokes a script on the Mac that writes the JSON. Matches the Sonos pattern. Cost: each writer needs a script on the Mac host and an SSH round-trip. Scaling to five writers adds five scripts and ties HA tightly to the host layout.

2. **Renderer exposes `POST /inputs/:name`.** HA `rest_command` POSTs the JSON body. Renderer validates shape, writes atomically. Cost: one endpoint; every writer is an HA-side YAML block.

Chose (2). HA is already talking to the renderer over HTTP (device fetch path is the same LAN channel). Adding `POST` to the same service lets us delete `ha/scripts/publish_inputs.sh`-style helpers before they proliferate. Authentication is a bearer token in `renderer_input_token` (new `secrets.yaml` entry). Atomicity: `write-then-rename`.

Sonos stays on its existing SSH path because it already works and the album-art fetch is co-located with the JSON write; porting it is out of scope here.

### Battery moves to a top-level `device` input

Current placement: `climateInput.inside.battery`. Wrong because (a) the kitchen climate sensor and the device are unrelated and fail independently, (b) only Summary ever read it. New placement:

```ts
deviceInput = {
  battery: { percentage: number, voltage?: number },
  build?: string,
  last_seen?: string,  // ISO timestamp; renderer doesn't use it but helpful for debugging
}
```

Every face reads `input.device.battery.percentage`. If the input file is missing (fresh install before HA publishes), the battery indicator falls back to the spec's missing-data treatment (em-dash).

### Clock cadence tracks mode, not wall-clock uniformly

Summary and Night have minute-tick ambitions. Writing `clock.json` every minute when the device is in Gallery is wasteful but cheap. The automation triggers every minute unconditionally, publishes the current minute-accurate payload; any smarter gating is a future optimization.

### HA secrets

One new secret: `renderer_input_token`. Generated once, stored in `ha/secrets.yaml` and `renderer/.env` (or passed via launchd's `EnvironmentVariables`). No rotation story for the initial ship.

## Risks / Trade-offs

- **Clock drift on the device display.** Minute-tick partial refreshes pull `/display/summary.png`, which reads `clock.json`. If the HA publisher lags, the displayed clock can be up to one minute off. Acceptable for an ambient display.
- **POST endpoint is a write surface.** LAN-only; bearer-token-authenticated; writes restricted to an allow-list of input names matching `^[a-z0-9_-]+$`. No path traversal. No shell-out. This is a small attack surface but not zero.
- **Re-seeding goldens.** The battery-indicator change flips pixels on four goldens. Not a behavioral risk, but reviewers of the snapshot diff should see only the indicator region changing.
- **Coupling HA availability to non-device-facing renders.** If HA's clock publisher stops, the simulated previews (via `/display/:mode/preview` in a browser) stay stuck on the last-published time. Since the device still gets a fresh PNG per wake (which re-reads files), this affects only the operator's dev view.

## Migration Plan

On apply:

1. Ship the renderer endpoint + `deviceInput` schema + `batteryIndicator` updates; generate `renderer_input_token`; add it to `ha/secrets.yaml`.
2. Ship the five HA `rest_command`s and their driving automations behind a feature flag (one `input_boolean.inkplate_publisher_enabled`, default on).
3. First deploy: watch `ha core logs | grep publish_inputs` and `curl http://${RENDERER_HOST}:8575/healthz` to confirm the writers land.
4. Re-seed golden PNGs once the writers are steady (`UPDATE_GOLDENS=1 npm test`).
5. Remove the old static fixtures from `renderer/inputs/` except the two image files (`gallery.jpg`, `nocturne.jpg`) — those remain as placeholders the renderer reads by path.

Rollback: disable the `input_boolean`, restore the committed fixtures, redeploy renderer without the endpoint. The device doesn't care which source populated the files.

## Open Questions

1. **Should the endpoint also expose `GET /inputs/:name`** for HA to self-verify its writes landed, or is the `200` response from `POST` sufficient? Leaning sufficient.
2. **Atomicity guarantees across reads and writes.** Writing is atomic (rename). Renderer reads via `fs.readFile` which is atomic at the filesystem layer. Simultaneous read-during-rename returns the old file; acceptable.
3. **Device-state republish cadence.** Today the device publishes only on wake (≤15-min cadence in Summary hours). HA can republish into `device.json` on each MQTT arrival; that's what we'll do. If the device sleeps longer than the indicator's tolerable staleness, we could add a "stale" marker, but not in this change.
