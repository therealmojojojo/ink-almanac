## ADDED Requirements

### Requirement: Input-publisher endpoint

The renderer SHALL expose `POST /inputs/:name` that writes a JSON body atomically to `RENDERER_INPUTS_DIR/${name}.json`.

- `:name` MUST match `^[a-z0-9_-]+$` and MUST be one of the allowed input names (`clock`, `weather`, `climate`, `hn`, `pairing`, `sonos`, `device`). Other values return 404.
- Requests MUST carry `Authorization: Bearer <token>` matching the renderer's `RENDERER_INPUT_TOKEN` environment variable. Missing header returns 401; mismatched token returns 403.
- Request body MUST be `application/json` and ≤ 256 KB. Larger bodies return 413.
- On success the renderer writes to a temp file in the inputs directory, then `rename`s it over the destination path, returning 204 No Content.
- The endpoint SHALL NOT validate the JSON body against a mode schema — schema validation happens at read time on the next `/display/*.png` request. This preserves the existing "inputs are loose, render enforces" contract.

#### Scenario: Authenticated write lands

- **WHEN** HA POSTs valid JSON to `/inputs/clock` with a matching bearer token
- **THEN** the renderer writes the file atomically and returns 204; a subsequent `GET /display/summary.png` reflects the new value

#### Scenario: Missing token rejected

- **WHEN** a POST arrives without an `Authorization` header
- **THEN** the renderer returns 401 and does not write to disk

#### Scenario: Wrong token rejected

- **WHEN** a POST arrives with an `Authorization: Bearer` token that does not match `RENDERER_INPUT_TOKEN`
- **THEN** the renderer returns 403 and does not write to disk

#### Scenario: Name outside allow-list rejected

- **WHEN** a POST arrives at `/inputs/secret` (a name not in the allow-list)
- **THEN** the renderer returns 404 and does not write to disk

#### Scenario: Oversized body rejected

- **WHEN** a POST body exceeds 256 KB
- **THEN** the renderer returns 413 and does not write to disk

### Requirement: Device input schema

Every mode SHALL accept a `device` input with the following schema:

```
device: {
  battery: {
    percentage: number (0..100, integer preferred)
    voltage?:   number
  }
  build?:     string
  last_seen?: string (ISO-8601)
}
```

The input is **optional at the schema level**: when `device.json` is absent, the renderer SHALL render the face with the battery indicator in its graceful-degradation treatment (em-dash label per `dashboard-faces`). A present-but-malformed `device.json` SHALL return 400 from `/display/*.png` per the existing Zod validation path.

The renderer SHALL pass `input.device?.battery?.percentage` to the shared `batteryIndicator` helper in every face module (`summary.ts`, `weather.ts`, `gallery.ts`, `night.ts`, `nowPlaying.ts`).

#### Scenario: All faces show the battery

- **WHEN** `device.json` contains `{battery: {percentage: 82}}` and any face is rendered
- **THEN** the top-right battery indicator shows `82%`, not an em-dash

#### Scenario: Missing device input degrades gracefully

- **WHEN** `device.json` is absent at render time
- **THEN** the renderer does NOT return 503; it renders the face with the em-dash battery treatment and logs a single info-level line naming the missing input

## MODIFIED Requirements

### Requirement: Inputs contract per mode

Each mode SHALL declare a typed input schema. The renderer SHALL reject any render request whose inputs do not match the schema, returning 400 with a detailed message.

Inputs come from configurable sources:
- A local JSON file at `RENDERER_INPUTS_DIR/<name>.json` — the canonical surface the renderer reads.
- `POST /inputs/:name` (see above) — the canonical surface HA writes.

Per-mode required inputs:
- `summary` ← `clock, weather, climate, hn, pairing, device`
- `weather` ← `clock, weather, device`
- `gallery` ← `clock, pairing, device`
- `night` ← `clock, weather, pairing, device`
- `now-playing` ← `clock, sonos, device`

`device` is listed as a required input across all faces because the shared battery indicator applies to all of them. When `device.json` is absent, the renderer SHALL NOT return 503 solely on that basis — the indicator falls back to its graceful-degradation treatment per `dashboard-faces`. Every other required input, if absent, returns 503 naming the missing file.

Zone character budgets are defined authoritatively by `dashboard-faces` and enforced at the renderer boundary per the Zone budgets requirement below.

#### Scenario: Missing required input (non-device)

- **WHEN** a render is requested for Summary and the weather input is unavailable
- **THEN** the response is status 503 with a message naming the missing input

#### Scenario: Missing device input is not fatal

- **WHEN** a render is requested and only `device.json` is missing
- **THEN** the response is status 200 with the face rendered and the battery indicator showing the graceful-degradation em-dash
