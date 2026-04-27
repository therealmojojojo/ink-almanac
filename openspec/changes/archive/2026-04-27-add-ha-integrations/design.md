## Context

Home Assistant is the nervous system of this project. It already runs on this Mac (as a HAOS VM with full supervisor). It has native integrations for everything the dashboard consumes — weather, Sonos, sun/moon, sensors, notifications — and it's where scheduling and overrides most naturally live. Putting that logic anywhere else would either reinvent HA's primitives (template sensors, automations, cron-like triggers) or create cross-boundary complexity.

This change introduces no new hardware, no new service; it wires what already exists, deploys it reproducibly from the repo, and exposes the contracts the rest of the system binds to.

## Goals / Non-Goals

**Goals:**
- A single source of truth (`ha/`) for HA configuration, deployed as a deliberate act.
- Live weather for both locations, indoor climate, Sonos, news, astro — every data input the faces consume.
- The schedule, overrides, and device-wake coordination working together as one system.
- Low operational overhead: deploy, reload, it works.

**Non-Goals:**
- Replacing HA. The custom logic supplements, not supplants.
- Building a dashboard of our own inside HA (Lovelace). The device is the dashboard; HA is the backend.
- Adding home-automation features beyond what the dashboard needs (lights, doors, etc.). If future house automation arrives, it lives in HA separately.
- Multi-home, multi-operator, multi-speaker configuration. Single kitchen, single operator.

## Decisions

### Deploy from repo via SSH, not in-VM editing

The repo is authoritative. Edits happen in the repo; `ha/deploy.sh` rsyncs to the VM via the SSH add-on. Rationale: version control, reproducibility, clean rollback, alignment with the operator's stated preference ("deliberate act rather than editing a file manually").

Alternative considered: SMB/Samba mount. Rejected because samba mounts on macOS are flaky and the "mount, rsync, unmount" pattern is clunky to script. SSH add-on + rsync is the native HA pattern.

### Custom fragments under `/config/custom/inkplate/`

The deploy places this project's files under a single subdirectory to avoid colliding with any other HA configuration the operator may add later. Rationale: hygiene, clear ownership boundary. Shared configuration like `secrets.yaml` goes to `/config/secrets.yaml` (the HA convention), but project-specific automations and sensors stay in the subdirectory.

### Weather: primary + fallback with HA's native composition

HA can expose multiple weather entities per location and compose preferred fields across them. We use this rather than writing our own fallback logic. Rationale: battle-tested, transparent, no bespoke code.

### Poetic weather line as its own capability

It could be folded into `ha-integrations` wholesale, but it's the one place in the runtime where an LLM is called regularly (beyond Now-Playing album-art processing, which is not LLM). Making it its own capability keeps the LLM behavior, the fallback pool, and the length/safety rules in a single auditable spec. When tuning costs or switching providers, the spec is easy to find.

### Hand-curated fallback pool is non-optional

Rationale: the LLM WILL fail occasionally (rate limits, outage, local Ollama not running). The fallback ensures Night mode always has a line, and the line always matches the weather. Without the pool, Night mode would either silently lose the line or display something inappropriate.

### Scheduled transitions via HA time triggers, not external cron

HA's time triggers are reliable, reloadable, and visible in the HA UI. External cron would require orchestration across the Mac host and the VM. Rationale: keep the schedule close to where state lives.

### Device-wake mechanism coordinated, not locked here

`add-device-firmware` defines whether wake is MQTT or HTTP. This spec asserts "HA issues a wake signal" without binding to the mechanism. When firmware chooses, both sides update. Rationale: the mechanism is an implementation detail of the device-HA pair, not a cross-project contract.

### News sources extensible

Initial deploy includes HN (mandatory) and at least one Romanian source. The YAML-driven config lets the operator add or remove sources without editing HA YAML by hand — just add an entry in `news_sources.yaml` and redeploy. Rationale: likely evolution; easier to accommodate early.

### Indoor climate left operator-choice

We don't ship a specific sensor — the operator may already have one, or may add an ESPHome DS18B20 later. The spec requires the two entities (`sensor.kitchen_temperature`, `sensor.kitchen_humidity`) and lets the operator satisfy them however. Rationale: hardware flexibility, respect existing deployments.

## Risks / Trade-offs

- **HAOS VM upgrades may break add-ons.** If the SSH add-on changes behavior, deploy breaks. Mitigation: deploy script validates connectivity before transferring; failure is loud and immediate.

- **Shell-command executions from HA.** The Sunday-night pairing trigger and potentially the poetic-weather-line generator call shell commands. If the Mac host is slow or offline, these fail. Mitigation: automation failure notifications; no runtime dependency on these (pre-generation and fallback pool mean rendering continues).

- **LLM cost creep.** The hourly poetic-weather-line with Claude Haiku is ~$0.001 per call × 8 calls/night × 365 = ~$3/year. Trivial, but confirm with prompt caching. Mitigation: spec requires small model and caching.

- **Weather provider API changes.** External APIs occasionally break. Mitigation: primary + fallback; HA logs expose issues quickly.

- **Sonos attribute variations by firmware.** Sonos firmware updates occasionally rename attributes or change formats. Mitigation: the attribute names referenced are HA integration-level abstractions, which tend to stay stable even when the underlying Sonos API shifts.

- **Secrets in plaintext.** `secrets.yaml` is plaintext on the HAOS VM. Standard HA risk. Mitigation: strict `.gitignore`; operator manages VM security.

- **Deploy race conditions.** If `deploy.sh` runs while HA is mid-automation, reloads can be ugly. Mitigation: HA reload is generally non-disruptive; the spec allows for brief instability at deploy time.

## Migration Plan

Assuming a fresh HAOS VM as it stands today:

1. Install SSH add-on; configure operator's SSH key.
2. Create `ha/` directory structure; populate with stubbed automations and sensors.
3. Write `deploy.sh`; run it for the first time — verifies SSH path.
4. Configure weather, climate, Sonos integrations (native setup in HA UI or via `configuration.yaml` fragments).
5. Wire template sensors that expose renderer inputs.
6. Implement the schedule automation and the override helper.
7. Implement the Sunday-night shell_command trigger.
8. Implement the poetic-weather-line automation with default Claude Haiku provider.
9. Implement low-battery notification.
10. Document each step in `ha/README.md`.

Rollback: delete `/config/custom/inkplate/` on the VM, remove relevant entries from `configuration.yaml`, reload. Native integrations (weather, Sonos) can be left in place — they don't harm anything.

## Open Questions

1. **Astro event data source.** in-the-sky.org scrape vs RSS vs a paid API. Leaning toward a simple RSS/scrape with 12h cache. Defer.

2. **Poetic weather line at runtime vs pre-generation.** Hourly runtime generation is cheap, so keep it runtime. Revisit if cost matters.

3. **Single HA automation or split into files.** HA reloads per-file; for maintainability, splitting seems better. Defer to implementation.

4. **Whether to expose the active override as an MQTT message or just as an entity.** If the device subscribes via MQTT, exposing via MQTT is convenient. Couple with `add-device-firmware`.

5. **Device-state reporting from firmware to HA.** Battery level, wake reason, last-fetch-timestamp — all useful. Defined in `add-device-firmware`; this capability consumes what's exposed.
