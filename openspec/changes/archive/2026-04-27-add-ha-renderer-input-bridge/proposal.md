## Why

The renderer reads `renderer/inputs/*.json` and renders. HA produces every value those files are supposed to carry (weather × 2 locations, HN + other news, astro, indoor climate, poetic-weather line, device battery). The bridge between the two is mostly missing: only `sonos.json` has a writer (`ha/scripts/fetch_sonos_art.sh` via SSH on track-change) and `pairing.json` has a Sunday-night writer that depends on an un-shipped `corpus pair` CLI. Weather, clock, climate, HN, and device state have **no publisher at all**. The fixtures currently on disk are 2-day-old demo content; the simulation is showing `THURSDAY · APRIL 16` at 21:47 while wall-clock is Saturday afternoon two days later, with `inside.battery = 87` hardcoded in the fixture.

This change closes the bridge. It also fixes a schema smell discovered while investigating: the device's own LiPo battery percentage is piggybacked on `climateInput.inside.battery` and is only honored by Summary — the four other faces render the battery indicator with `undefined` (em-dash label). That placement is wrong (battery is device state, not climate) and the per-face wiring is incomplete.

## What Changes

- Add a renderer endpoint `POST /inputs/:name` that atomically writes a JSON body to `RENDERER_INPUTS_DIR/${name}.json`. Authenticated by a shared token from a new secret `renderer_input_token`.
- Split **device state** out of `climateInput` into a new top-level input: `device.json` carrying `{battery: {percentage, voltage?}, build?, last_seen?}`. All five face modes read `device.battery.percentage` for the battery indicator; `climateInput.inside.battery` is removed.
- Add one HA `rest_command` per input and the automations that call them:
  - `weather.json` — trigger: any of the renderer-facing template sensors change; also time-pattern hourly re-publish.
  - `clock.json` — trigger: time-pattern every minute while the device is in a minute-tick-eligible mode; otherwise every 5 minutes.
  - `climate.json` — trigger: kitchen climate sensor state change (when that sensor ships; today this input's body is `{inside: {temp, humidity?}}` only).
  - `hn.json` — trigger: `sensor.inkplate_hn_top5` attribute update.
  - `device.json` — trigger: `inkplate/state/device` MQTT retained-message arrival; republish on HA start.
  - `pairing.json` — unchanged in transport (Sunday-night generator on the Mac host), but documented alongside the other writers in the bridge catalog.
- Wire initial-publish on HA start so a fresh-booted HA propagates state without waiting for triggers.
- Update the shared `batteryIndicator` call sites so every face passes the device input value, not `undefined`.

## Capabilities

### Modified Capabilities

- **`rendering-pipeline`** — adds `POST /inputs/:name`, adds the device input schema, modifies the per-mode input set (device added to all five; `climate.inside.battery` dropped).
- **`dashboard-faces`** — the "Shared conventions" requirement's battery indicator now pulls from the device input on every face, not from per-mode arbitrary sources.
- **`ha-integrations`** — adds a Renderer-input publisher requirement covering the five HA→renderer writers.

### New Capabilities

None.

## Impact

- **Code**: new `POST /inputs/:name` handler in `renderer/src/server.ts`; new `deviceInput` in `src/modes/schema.ts`; `batteryIndicator(undefined)` call sites in `weather.ts`, `gallery.ts`, `night.ts`, `nowPlaying.ts` switched to `batteryIndicator(input.device.battery.percentage)`; `climateInput.inside.battery` removed; new `ha/scripts/publish_inputs.sh` helper used by `rest_command`s (or direct `rest_command` bodies).
- **Secrets**: new `renderer_input_token` in `ha/secrets.yaml` and `firmware/include/secrets.h` is unaffected (device never writes inputs).
- **Fixtures**: `test/fixtures/*.json` get a `device.json` companion; climate fixtures lose `battery`.
- **Goldens**: re-seed required for the four faces that were rendering `—` — they now show an actual percentage.
- **Docs**: `ha/docs/architecture.md` gains the input-publisher catalog; `renderer/README.md` "Inputs" table gains the `device` row and the `POST /inputs/:name` endpoint.
- **Does not change**: MQTT topic contract between HA and device; device firmware; the device's own battery reporting via `inkplate/state/device` (that's upstream of this change).
