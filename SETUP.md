# Setup

Bringing up an Inkplate dashboard from scratch involves four pieces:

1. **Renderer host** (a Mac or Linux box that's always-on)
2. **Home Assistant** (HAOS VM is assumed; HA Container/Supervised needs deploy script tweaks)
3. **Inkplate 10** (the device itself)
4. **Corpus + pairing tooling** (the content pipeline; runs on the renderer host)

Total wall-clock time, first install: ~2 hours of focused work, plus 15-30 min of e-ink waveform-calibration on the device.

If you're picking up a working install, skip to [Day-to-day operations](#day-to-day-operations) at the bottom.

## 0. Substitution layer (`local-overrides.env`)

Operator-specific values (LAN IPs, weather location names, paths,
operator username) are kept out of the tracked tree. Tracked files use
`${VAR}` placeholders; real values live in `local-overrides.env`
(gitignored), which is sourced by `ha/deploy.sh` and substituted into
the deploy tarball before sending to HA. Same pattern can be used by
any build/deploy step that needs to resolve placeholders.

Before doing any other setup:

```sh
cp local-overrides.env.example local-overrides.env
# edit local-overrides.env — fill in:
#   RENDERER_HOST   IP/hostname of the always-on Mac/Linux renderer host
#   HA_HOST         IP/hostname of the HAOS VM
#   Z2M_HOST        IP/hostname of zigbee2mqtt (or leave default)
#   PLACE_A_NAME    display name of your primary weather location
#   PLACE_A_SLUG    HA-entity-id-safe slug for the same (lowercase, no diacritics)
#   PLACE_B_NAME    secondary weather location
#   PLACE_B_SLUG    same
#   INKPLATE_REPO   absolute path to this clone on the renderer host
#   OPERATOR_USER   the renderer-host username (usually $USER)
```

Three other operator-specific live files **also** stay out of git, each
copied once from a tracked `.example` template:

| Live file (gitignored) | Template |
|---|---|
| `firmware/include/secrets.h` | `firmware/include/secrets.h.example` |
| `renderer/launchd/com.inkplate.renderer.plist` | `renderer/launchd/com.inkplate.renderer.plist.example` |
| `ha/secrets.yaml` | `ha/secrets.yaml.example` |

They contain credentials (WiFi pass, MQTT pass, HA long-lived token,
renderer bearer token) — never let them enter git. The `local-overrides.env`
holds the non-credential operator-specific values. Together they cover
every editable runtime constant.

## Prerequisites

- A Mac or Linux box with Node ≥20 and Python ≥3.10. (The renderer is tested on Node 25; older may work.)
- Home Assistant (HAOS recommended) with these add-ons installed:
  - **Mosquitto broker** (for device MQTT).
  - **Advanced SSH & Web Terminal** (so the deploy script can rsync into `/config/`).
- An Inkplate 10 (Soldered version) + a USB-C cable.
- PlatformIO (`pip install platformio` or VSCode extension) for building/uploading firmware.
- A WiFi network the device, the renderer host, and HA can all reach. (Pure LAN — nothing here phones home for control-plane traffic. Anthropic API is only used for daily corpus seed generation, an offline tool.)

## 1. Renderer (on the Mac)

The renderer is a Hono server that listens on port **8575** for `GET /display/:mode.png` and `POST /inputs/:name`. It reads input JSON files from `renderer/inputs/`, fires a Playwright/Chromium tab against an HTML template, screenshots 1200×825, and returns a single-channel 8-bit PNG.

```sh
cd renderer
npm install                         # installs hono, playwright, sharp, etc.
npx playwright install chromium     # ~150 MB, one-time
npm start                           # foreground; serves on :8575
```

Sanity-check: `curl -o /tmp/test.png http://127.0.0.1:8575/display/weather.png` should return a 1200×825 PNG. If you don't have a real `pairing.json` yet, weather/clock will use stub data and the gallery face will show a placeholder dash.

### Auto-start the renderer

For production, the renderer needs to be running whenever HA expects to publish to it. The repo includes a launchd plist for macOS:

```sh
cp renderer/launchd/com.inkplate.renderer.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.inkplate.renderer.plist
```

Edit the plist before loading to set:

- `INKPLATE_RENDERER_DIR` to your absolute repo path
- `RENDERER_INPUT_TOKEN` to a fresh token (any 30+ char random string; you'll paste it into HA's secrets next)

`KeepAlive: true` + `ThrottleInterval: 10` mean the renderer auto-restarts on crash, with a 10 s backoff to avoid loops. Logs at `/tmp/inkplate-renderer.{out,err}.log`.

For Linux, write an equivalent systemd unit; `npm start` is the only command.

## 2. Home Assistant

The HA side is a tree of YAML fragments (automations, sensors, integrations, helpers, scripts) that gets rsynced into `/config/custom/inkplate/` on the HAOS VM.

### Add-on prerequisites

In the HA UI, install:

- **Mosquitto broker** — and create a user (e.g. `inkplate`) with a password. You'll paste both into device firmware secrets later.
- **Advanced SSH & Web Terminal** — and put your operator workstation's SSH public key into the add-on config under `authorized_keys`. Note the SSH port the add-on uses (default 2222).

### Wire `configuration.yaml`

Edit `/config/configuration.yaml` (over the SSH add-on) and add:

```yaml
homeassistant:
  packages: !include_dir_named custom/inkplate/integrations
automation inkplate: !include_dir_merge_list custom/inkplate/automations
sensor inkplate:    !include_dir_merge_list custom/inkplate/sensors
```

### Fill secrets

Locally:

```sh
cp ha/secrets.yaml.example ha/secrets.yaml
# edit ha/secrets.yaml — fill in:
#   ha_long_lived_token (HA UI → profile → Long-lived access tokens)
#   renderer_input_auth_header (literal "Bearer <RENDERER_INPUT_TOKEN>" from step 1)
#   anthropic_api_key (only if you'll regenerate the corpus seed; not used at runtime)
#   sonos / weather / location / etc. — see secrets.yaml.example for the full list
```

The deploy script copies `ha/secrets.yaml` to `/config/custom/inkplate/secrets.yaml` (NOT to `/config/secrets.yaml`). HA's `!secret` tag walks upward, so this scoping keeps your existing top-level secrets untouched.

### Deploy

```sh
make deploy-ha            # SSH+rsync, ha core check, ha core restart
```

Override per-environment with env vars:

```sh
HA_HOST=${HA_HOST} HA_SSH_PORT=2222 HA_USER=root HA_SSH_KEY=~/.ssh/id_ed25519 make deploy-ha
```

After deploy, in the HA UI verify:

- Settings → Devices & Services → Helpers → `Inkplate publisher enabled` is **on**. (This is the master kill switch for all renderer publishers; if it's off, nothing flows.)
- Settings → Automations → search "Inkplate" → all should be enabled. Specifically `automation.inkplate_per_tier_face_alternation_tick`, `automation.inkplate_publish_clock`, `automation.inkplate_06_00_publish_today_s_triplet`.

## 3. Inkplate firmware

```sh
cd firmware
cp include/secrets.h.example include/secrets.h
# edit include/secrets.h — fill in:
#   INKPLATE_WIFI_SSID / PASSWORD
#   INKPLATE_MQTT_HOST (your HAOS VM IP) / USER / PASS / PORT (typically 1883)
#   INKPLATE_RENDERER_BASE (e.g. "http://${RENDERER_HOST}:8575")

# Plug Inkplate 10 in via USB, then:
pio run -e inkplate10 --target upload
pio device monitor -b 115200    # tail serial logs (optional but useful for first boot)
```

Cold boot timeline you should see in the serial log:

1. WiFi connect (~2-5 s).
2. NTP resync (~600 ms).
3. MQTT connect.
4. `clock-zone fetch stored x=… y=… fs=…` for whatever the cold-boot face is.
5. First Full draw.
6. Post-Full zone cleanup (two partial pulses).
7. Deep sleep arming.

If WiFi assoc fails 3× in a row the device draws an 80×80 corner-indicator and sleeps; check `secrets.h` and signal strength.

## 4. Corpus + pairing

The corpus is the pile of YAML sidecars under `corpus/` plus their binary attachments (images and text bodies for personal-library items). Sidecars are version-controlled; binaries are not (see `corpus/_manifest.json`).

```sh
pip install -e pairing                     # registers the `corpus` CLI
corpus validate                            # structural + taxonomy + manifest
corpus validate --full                     # also hash-verify every binary
corpus audit --out corpus/_audits/audit-$(date +%F).md
```

If you're forking, the corpus that ships with the repo reflects the original curator's taste. To swap your own:

1. Delete `corpus/_triplets/*.yaml` and `corpus/_manifest.json`.
2. Drop new sidecars into the appropriate tier directory:
   - `corpus/public_domain/` — out-of-copyright works (binaries optional, can be web-fetched on demand).
   - `corpus/personal_library/` — in-copyright works for private fair-use display (binaries off-tree, fetched once).
   - `corpus/cc0/` — operator-cleared additions.
3. Run `corpus validate` until it passes.
4. Generate triplets via `python3 pairing/build_triplets.py --apply` (the picker is conservative; it'll reject items that don't pass the panel-fidelity gate).
5. Reset `pairing/_state/triplet_epoch.json` to today's date.

The taxonomy (`corpus/_taxonomy/{mood,register,themes,form}.yaml`) is closed by default. Adding terms requires going through the amendment procedure documented in `openspec/specs/corpus-taxonomy/`.

## Day-to-day operations

### Force a fresh render (e.g. after editing a corpus sidecar)

```sh
python3 pairing/publish_today.py            # re-stages today's triplet to renderer/inputs/
curl http://127.0.0.1:8575/display/summary.png > /dev/null   # warm the renderer cache
```

### Override the daily triplet (e.g. for testing)

```sh
python3 pairing/publish_today.py --id <triplet-id>   # forces a specific triplet, ignores rotation
```

`<triplet-id>` is the basename of any file under `corpus/_triplets/`.

### Re-bake the on-device clock glyphs (after editing live-face CSS)

```sh
cd renderer && npm run bake:clock-glyphs
cd ../firmware && pio run -e inkplate10 --target upload
```

The bake reads each preset's font + CSS settings, emits `firmware/src/generated/clock_glyphs.{h,cpp}`, then the firmware build pulls them in.

### Tail the device

```sh
cd firmware && pio device monitor -b 115200
```

Shows the firmware's per-tick log: wake reason, path decision, WiFi/MQTT outcome, partial cycles. `[ntp]`, `[partial]`, `[tick]`, `[IMU]` prefixes group the output.

### Rotate a corpus item

```sh
corpus refetch                          # picks panel_verdict=reject items, re-fetches with a different web URL
corpus validate --full                  # confirm the new binary hashes match the manifest
```

### Roll back the HA deploy

```sh
ssh root@<HA_HOST> -p <HA_SSH_PORT>
rm -rf /config/custom/inkplate
# remove the three include lines from /config/configuration.yaml
ha core check && ha core restart
```

Native HA integrations (weather, sun, moon, Sonos) can stay — they're idempotent and don't depend on this project.

### What to do when the smart pill changes after a redeploy

It shouldn't any more — the live-LLM regen pipeline was removed. If it does, check `renderer/inputs/news.json` mtime; the only thing that should write it is `pairing/publish_today.py` at 06:00 EEST. If something else has touched it, that's the culprit.

### What to do when the panel sticks at one face

Either the alternation tick stopped firing or the device isn't waking. Check:

```sh
# Did the alternation tick fire recently?
curl -H "Authorization: Bearer $HA_TOKEN" \
     "http://$HA_HOST:8123/api/states/automation.inkplate_per_tier_face_alternation_tick" | jq .

# Is the publisher kill switch on?
curl -H "Authorization: Bearer $HA_TOKEN" \
     "http://$HA_HOST:8123/api/states/input_boolean.inkplate_publisher_enabled" | jq .

# Is the device heartbeating?
mosquitto_sub -h $HA_HOST -t 'inkplate/state/device' -v -C 1
```

If none of those flag a problem, charge the device — battery dropout looks identical to "stuck" because the panel is bistable.

## Further reading

- [`ARCHITECTURE.md`](ARCHITECTURE.md) — system diagram, data flow, design decisions.
- [`firmware/README.md`](firmware/README.md) — firmware internals.
- [`renderer/README.md`](renderer/README.md) — renderer endpoints + template structure.
- [`ha/README.md`](ha/README.md) — HA automations and override state machine.
- [`pairing/README.md`](pairing/README.md) — corpus CLI reference.
