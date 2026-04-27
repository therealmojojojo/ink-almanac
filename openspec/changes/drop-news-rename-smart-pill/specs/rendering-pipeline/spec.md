# rendering-pipeline — delta

## MODIFIED Requirements

### Requirement: Per-mode input contract

Each mode SHALL declare a typed input schema. The renderer SHALL reject any render request whose inputs do not match the schema, returning 400 with a detailed message.

Inputs come from configurable sources:
- A local JSON file at `RENDERER_INPUTS_DIR/<name>.json` — the canonical surface the renderer reads.
- `POST /inputs/:name` (see Input-publisher endpoint) — the canonical surface HA writes.

Per-mode required inputs:
- `summary` ← `clock, weather, climate, smart_pill, pairing, device`
- `weather` ← `clock, weather, device`
- `gallery` ← `clock, pairing, device`
- `night` ← `clock, weather, pairing, device`
- `now-playing` ← `clock, sonos, device`

`device` is listed as a required input across all faces because the shared battery indicator applies to all of them. When `device.json` is absent, the renderer SHALL NOT return 503 solely on that basis — the indicator falls back to its graceful-degradation treatment per `dashboard-faces`. Every other required input, if absent, returns 503 naming the missing file.

The `smart_pill` input SHALL carry the body text for Summary's smart-pill section (a deep-dive entry — word-of-the-day or concept-of-the-day — bound to the day's companion text). The previous name `news` is retired; it was residue from an earlier multi-source RSS design that no longer exists. Likewise the previous `hn` input (Hacker News top-N) is retired; the device does not surface news of any kind.

Zone character budgets are defined authoritatively by `dashboard-faces` and enforced at the renderer boundary per the Zone budgets requirement below.

#### Scenario: Missing required smart_pill input

- **WHEN** a client requests `GET /display/summary.png` and `RENDERER_INPUTS_DIR/smart_pill.json` is absent
- **THEN** the renderer returns 503 with a body naming the missing file (`smart_pill.json`); the response is not cached

#### Scenario: Legacy `news` input present is ignored

- **WHEN** an old `RENDERER_INPUTS_DIR/news.json` exists alongside `smart_pill.json`
- **THEN** the renderer reads `smart_pill.json` and ignores `news.json`; `news` is not a valid input name

### Requirement: Input-publisher endpoint

The renderer SHALL expose `POST /inputs/:name` that writes a JSON body atomically to `RENDERER_INPUTS_DIR/${name}.json`.

- `:name` MUST match `^[a-z0-9_-]+$` and MUST be one of the allowed input names (`clock`, `weather`, `climate`, `smart_pill`, `pairing`, `sonos`, `device`). Other values return 404.
- Requests MUST carry `Authorization: Bearer <token>` matching the renderer's `RENDERER_INPUT_TOKEN` environment variable. Missing header returns 401; mismatched token returns 403.
- Request body MUST be `application/json` and ≤ 256 KB. Larger bodies return 413.
- On success the renderer writes to a temp file in the inputs directory, then `rename`s it over the destination path, returning 204 No Content.
- The endpoint SHALL NOT validate the JSON body against a mode schema — schema validation happens at read time on the next `/display/*.png` request. This preserves the existing "inputs are loose, render enforces" contract.

The legacy input names `news` and `hn` are no longer accepted; requests with those `:name` values return 404.

#### Scenario: Authenticated write to smart_pill lands

- **WHEN** the pairing publisher PUTs a valid JSON body to `/inputs/smart_pill` with a matching bearer token
- **THEN** the renderer writes the file atomically and returns 204; a subsequent `GET /display/summary.png` reflects the new body

#### Scenario: Legacy `news` POST rejected

- **WHEN** any client POSTs to `/inputs/news`
- **THEN** the renderer returns 404 because `news` is no longer in the input-name allowlist

## REMOVED Requirements

None at the requirement level. The retired `news` and `hn` input names are folded into the modified Per-mode input contract requirement above; the smart-pill body's transport contract is preserved (zone, schema shape modulo the optional flatten, file location), only the name changes.
