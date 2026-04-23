## Why

Every face needs live data, every override needs a trigger, every scheduled transition needs an orchestrator. Home Assistant is where all of this belongs: it already runs on this Mac (as a HAOS VM), already integrates with Sonos, weather, and RESTful services, and already provides the scheduling primitives the project needs.

Without this capability, the renderer has nothing to render, the Inkplate has nothing to fetch, and the scheduled modes are just promises. This change is where the dashboard becomes a live system.

## What Changes

- Introduce the `ha/` directory in the repo as the source of truth for HA configuration fragments (sensors, automations, scripts, REST commands), deployed to the HAOS VM via `ha/deploy.sh` using the HA SSH add-on.
- Set up the **SSH add-on** path: document the key-exchange, the deploy script, the reload steps.
- Configure **weather for both locations** — ${PLACE_A_NAME} (home, 95m) and ${PLACE_B_NAME} (mountains, 900m) — using a primary provider (MET.no or OpenWeatherMap) and a secondary fallback if the primary becomes unavailable.
- Configure **indoor climate** sensors — coupled to an ESP-based sensor (already in the house, or trivially added) reporting temp and humidity.
- Configure the **Sonos integration** for `media_player.kitchen_sonos` with the attributes Now-Playing consumes (state, media_content_id, title, artist, album, entity_picture, source).
- Configure a **Hacker News REST sensor** refreshing every 30 minutes, exposing top stories for Summary's news zone.
- Configure **other news sources** — at minimum one Romanian outlet. Format configurable in `ha/config/news_sources.yaml`.
- Configure an **astro sensor**: sunrise/sunset/moon-phase via `sun.sun` and `moon` integrations; tonight's astronomical event via an RSS feed or scheduled scrape of in-the-sky.org (implementation-detail of the change).
- Implement the **scheduled-mode automation**: at 06:30, 10:00, 22:00 transitions, HA determines the new scheduled face and issues a wake signal to the device unless a higher-precedence override is active.
- Implement the **Sunday-night pairing-generation trigger**: executes `corpus pair generate-week` via `shell_command`; sends an HA notification when complete.
- Implement the **poetic-weather-line generator** for Night mode: hourly LLM call (local or cloud, configurable) producing a ≤32-char italic line from the current weather, cached to a state file the renderer reads.
- Implement the **low-battery notification**: at <20% battery (reported by the device), send an HA notification to the operator's phone.
- Implement the **device wake endpoint contract**: HA issues wake calls via the mechanism chosen by `add-device-firmware` (MQTT or HTTP).
- Implement the **cross-component state holder**: a small set of HA helper entities tracking the currently-active override (used by `add-now-playing-mode`).

## Capabilities

### New Capabilities

- `ha-integrations`: The Home Assistant configuration that makes the dashboard live — sensors, automations, REST commands, helper entities, scheduling, and the deploy path.
- `poetic-weather-line`: The hourly LLM-generated Night-mode line produced from current weather, cached to a file path consumed by the renderer. Kept separate because it is the one legitimate runtime LLM call in the system (beyond ingestion).

### Modified Capabilities

None. Consumes existing ratified capabilities; does not modify them.

## Impact

- **New directory**: `ha/` with `automations/`, `sensors/`, `scripts/`, `rest_commands.yaml`, `secrets.yaml.example`, `deploy.sh`, `README.md`.
- **New deploy mechanism**: `make deploy-ha` (or equivalent) that rsyncs `ha/` into the HAOS VM's `/config/custom/inkplate/` via SSH and reloads HA configuration.
- **HA add-ons required**: SSH & Web Terminal (for deploy), optionally File Editor (for diagnostic inspection). MQTT Broker add-on may be required depending on the device-wake mechanism.
- **New HA entities**: template sensors per zone, helper entities for state-holding, REST sensors for HN and news, scraped sensors for astro events.
- **New credentials** (in `secrets.yaml`): weather API key, Sonos token (handled by native integration), LLM credentials for the poetic-weather-line if using Claude.
- **LAN network requirement**: the HAOS VM can reach the Mac host at port 8575 (renderer). Documented; verified at deploy time.
- **No changes** to corpus, rendering pipeline, pairing pipeline, or firmware specs. This change binds to the contracts they already ratify.
