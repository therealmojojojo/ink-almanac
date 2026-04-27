# Inkplate

A literary kitchen-fridge dashboard on an Inkplate 10 e-ink panel. Each day picks a curated *triplet* — anchor text, summary delight, gallery image — and rotates Summary↔Weather and Gallery↔Weather faces through the day. A Sonos integration takes over while music plays; a tap on the panel flips the alternation phase. Battery-powered, ~3 months between charges.

![Status: working prototype, single-installation production](https://img.shields.io/badge/status-working%20prototype-yellow)

## What it does

- **Six faces**, picked by a per-tier alternation engine in Home Assistant:
  - **Summary** (06:30–10:00) — giant Didone clock + delight cell + smart-pill word study.
  - **Weather** — current conditions for two locations, 5-day forecast, "poetic weather line" (LLM-generated daily), astronomy events.
  - **Gallery (visual)** — full-bleed image with title/attribution caption.
  - **Gallery (text)** — typeset poem / aphorism / fragment.
  - **Night** (22:00–06:30) — natural-language clock ("quarter past eleven") + nocturne thumbnail.
  - **Now-Playing** — Sonos album art + track info, takes priority while music plays.
- **Daily triplet pipeline**: a curated corpus of images and texts (sidecared YAML, public-domain + personal-library tiers) is paired off-line into ~1000 triplets; one is published each day at 06:00.
- **Smart pill**: a 400-character word/concept gloss, LLM-pre-built per summary item, deterministic across the day.
- **Partial-refresh clock**: every minute the clock zone updates via a 1-bit partial pulse — no full-screen flash.
- **Tap acknowledgment**: tap the frame, a small dot badge appears next to the battery indicator within ~450 ms — well before the face change lands.
- **Always-fresh time**: NTP re-syncs on every WiFi-up, so the panel can't drift.

## Hardware

| Part | Notes |
|---|---|
| **Inkplate 10 (Soldered)** | 1200 × 825, 3-bit greyscale (8 shades), no hue. Custom HAL wraps Soldered's library. |
| ESP32-WROVER (built-in to Inkplate 10) | PSRAM required for 3-bit framebuffer + image decode. |
| **LSM6DSO IMU** | I²C 0x6B. Tap detector wakes ESP32 via INT1 → GPIO 36 (shared with the wake button). |
| Li-ion battery | Tested with 5000 mAh; ~3 months between charges depending on tier cadence. |
| Mac (always-on) | Hosts the Node renderer (Playwright + Chromium) and runs the daily pairing script. |
| HAOS VM (e.g. Synology, Pi) | Home Assistant + Mosquitto broker + the Advanced SSH add-on. |

## Architecture (10,000 ft)

```
                 ┌─────────────┐
   corpus/  ──▶  │   pairing   │  ──▶  renderer/inputs/{pairing,news}.json
  (YAML +        │  (Python,   │       + companion.jpg, gallery.jpg, nocturne.jpg
   binaries)     │   06:00)    │
                 └─────────────┘
                       │ (one triplet/day)
                       ▼
   HA  ──┬─▶  publishers  ──▶  renderer/inputs/*.json (clock, weather, sonos, news, device)
         ├─▶  schedule alternation tick (every 15 m, decides current face)
         └─▶  gesture handler (tap → flip alternation phase)
                       │
                       ▼  publishes inkplate/command/active_mode (retained MQTT)
                       │
                 ┌────────────┐
                 │   device   │  ◀── PNG fetch ──▶ renderer (Mac, port 8575)
                 │ (Inkplate) │      Playwright → Chromium → 1200×825 8-bit greyscale PNG
                 └────────────┘
                  │       ▲
                  ▼       │
           heartbeat   tap → IMU INT1
        inkplate/state/*    └─▶ ack glyph + gesture publish
```

The **renderer** is the only stateful service of consequence. It accepts JSON pushes from HA at `POST /inputs/:name`, reads them on each `GET /display/:mode.png` request, runs templates through Playwright/Chromium, and returns an 8-bit greyscale PNG (the device handles palette dithering itself). It also exposes `/display/:mode/clock-zone.json` so the firmware can pin its 1-bit partial-update digits at the same pixels the Full painted.

The **device firmware** is mostly pure-logic over a HAL interface. Every wake (timer, IMU tap, cold-boot) reads the schedule planner in `firmware/include/wake.h` to decide Full / Partial / Poll / Skip. Partials offline-render the clock zone at the device's RTC time; Fulls fetch a fresh PNG over WiFi.

A deeper diagram + data-flow walkthrough is in [`ARCHITECTURE.md`](ARCHITECTURE.md).

## Repo layout

```
inkplate/
├── README.md         ← you are here
├── ARCHITECTURE.md   ← system diagram, data flow, design decisions
├── SETUP.md          ← operator quick-start (corpus → renderer → HA → device)
├── CLAUDE.md         ← repo conventions for AI / human contributors
│
├── corpus/           Curated images + texts (sidecar YAML; binaries off-tree)
├── pairing/          Python: corpus validator, daily triplet picker, ingestion CLI
├── renderer/         Node + Playwright: HTML templates → 1200×825 PNGs
├── ha/               Home Assistant config: automations, sensors, integrations
├── firmware/         Inkplate 10 firmware (PlatformIO + custom HAL) + host simulator
└── openspec/         Specs (ratified) + change proposals (in-flight) + archive
```

Each area has its own `README.md` and (most) a `docs/` with deeper guides:

- [`corpus/README.md`](corpus/README.md) — sidecar schema, rights tiers, manifest
- [`pairing/README.md`](pairing/README.md) — CLI reference, ingestion workflow
- [`renderer/README.md`](renderer/README.md) — endpoints, template structure, Playwright setup
- [`ha/README.md`](ha/README.md) — deployment, override state machine, troubleshooting
- [`firmware/README.md`](firmware/README.md) — wake schedule, partial-refresh clock, tap handling, host simulator

## Quick-start

For a clean install across all four hosts, follow [`SETUP.md`](SETUP.md). The TL;DR per area:

```sh
# Renderer (on the Mac that drives the device)
cd renderer && npm install && npm start                      # serves on :8575

# HA config (deploys to your HAOS VM over SSH)
make deploy-ha                                               # rsync + ha core restart

# Firmware (with Inkplate 10 plugged into USB)
cd firmware && pio run -e inkplate10 --target upload

# Pairing tooling
pip install -e pairing                                       # adds the `corpus` CLI
corpus validate                                              # sanity-check the corpus
```

## Status

Working in single-installation production, but the project is opinionated and not yet a turnkey kit:

- **Corpus**: 1,023 triplets across the personal/PD library; the curator's taste is baked in. You can swap your own corpus, but the taxonomy and rights tiers are project-specific.
- **Hardware**: Inkplate 10 only. The HAL abstraction (`firmware/include/hal/`) is clean enough that another e-ink board could be added, but no other targets exist.
- **HA bias**: deploy assumes HAOS VM with the Advanced SSH add-on. Bare-metal Home Assistant or HA Container would need [`ha/deploy.sh`](ha/deploy.sh) tweaks.
- **OpenSpec**: most originally-planned features have shipped; some specs are stale (the code is the source of truth — see archived changes in [`openspec/archive/`](openspec/archive/)).

What works end-to-end as of this writing:

- Daily triplet rotation, Summary / Weather / Gallery (visual + text) / Night / Now-Playing faces.
- Per-tier face alternation in HA, with double-tap → flip phase, single-tap → same.
- Partial-refresh clock zone every minute on Summary / Weather / Gallery (split + landscape) / Now-Playing / Gallery-Text.
- Sonos override with track-art rendering, paused-music linger, tap-during-music → 60 s peek to schedule.
- Post-OTA recovery, IMU tap detection on the wire-tied frame, NTP resync, listen-with-retry on the renderer, EADDRINUSE crash-loop guard.

Known limitations:

- Renderer is a single point of failure (Mac sleeping = panel doesn't update). Move to a Pi if uptime matters.
- Battery percentage formula caps at 4.15 V → 100 %, so the meter sits at "100 %" for the first ~10 % of discharge. Cosmetic, not functional.
- Single-tap and double-tap are unified in HA (the wire-tied frame mount can ring as either depending on tap force; treating them the same eliminates "tap didn't register" cases). If you want them distinct, undo `ha/automations/gesture_override.yaml`.

## Contributing

This is a personal project, but the architecture is generic enough to fork. For a tour of the codebase before editing, start with [`CLAUDE.md`](CLAUDE.md) (which defines repo conventions and OpenSpec governance), then the area-specific READMEs. PRs welcome but not actively solicited.

## License

No formal license file. Treat as a private build until I decide what to publish under. Third-party libraries (Playwright, Hono, Soldered Inkplate, paho-mqtt, etc.) retain their own licenses — see each area's package manifest.
