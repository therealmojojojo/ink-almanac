# ha/ — Home Assistant configuration for the Inkplate dashboard

This is the source of truth for the HA side of the system. Deployed to the HAOS VM as
`/config/custom/inkplate/` by `ha/deploy.sh`.

## Layout

```
ha/
├── automations/          YAML automations (schedule, pairing trigger, poetic-weather, low-battery, sleep-strategy)
├── sensors/              template + rest + scrape sensors (weather, HN, news, astro, kitchen climate)
├── scripts/              helper scripts invoked via shell_command (LLM line generator, pairing runner)
├── config/               operator-editable config (news_sources.yaml, poetic_weather_line.yaml, night_fallback_lines.yaml)
├── integrations/         top-level integration snippets included from configuration.yaml
├── state/                runtime state written by automations (poetic_weather.txt) — gitignored
├── docs/                 architecture, deploy, troubleshooting, sleep-strategy
├── deploy.sh             rsync + reload over SSH
├── secrets.yaml.example  copy to secrets.yaml (gitignored) and fill in
└── README.md
```

## One-time setup (HAOS VM)

1. **SSH & Web Terminal add-on.** Install from the HA Add-on store. Set the operator's public key in the add-on config (`Authorized keys`). Enable *Protection mode off* so the add-on can reload HA configuration. Start the add-on and note the port (default `2222`).

2. **Inclusion in `configuration.yaml`.** Edit the VM's `/config/configuration.yaml` (via the SSH add-on) to include the project fragments:

   ```yaml
   homeassistant:
     packages: !include_dir_named custom/inkplate/integrations
   automation inkplate: !include_dir_merge_list custom/inkplate/automations
   sensor inkplate: !include_dir_merge_list custom/inkplate/sensors
   ```

   `shell_command:` lives inside `integrations/shell_commands.yaml` and is
   picked up by the `packages` line — do not `!include` it a second time.

3. **Secrets.** Copy `ha/secrets.yaml.example` → `ha/secrets.yaml`, fill in, then deploy (the deploy script copies it to `/config/secrets.yaml` on the VM).

4. **Add-ons required / recommended:**
   - **Mosquitto broker** — the device talks MQTT (`inkplate/command/*`, `inkplate/state/*`).
   - **Advanced SSH & Web Terminal** — deploy path.
   - **File editor** *(optional)* — diagnostic inspection only; **do not edit files in-VM**; in-VM edits are drift.

## Deploy

```bash
make deploy-ha
# or
./ha/deploy.sh
```

The script:
1. Verifies the SSH key works against the HAOS VM.
2. rsync's `ha/` → `/config/custom/inkplate/` (secrets.yaml separately → `/config/secrets.yaml`).
3. Calls `ha core reload` over SSH to pick up automations/sensors.
4. Tails the HA log for any load errors.

## State semantics: `input_text.active_override`

Tracked as a helper in `integrations/helpers.yaml`. Allowed values and precedence (highest to lowest):

| Value | Meaning | Precedence |
|---|---|---|
| `now_playing` | Sonos is playing in the kitchen; Now-Playing face is shown | 1 (highest) |
| `weather_peek` | Single-tap gesture requested Weather face for a 5-min window | 2 |
| `summary_gallery_toggle` | Double-tap toggled Summary ↔ Gallery until next schedule boundary | 3 |
| `schedule` | No override; the time-of-day schedule drives the active face | 4 (lowest) |

`input_text.prior_override` records the value displaced by `now_playing` so Now-Playing can restore it when music stops and linger ends.

The scheduled-mode automation (`automations/schedule.yaml`) always updates an internal "current scheduled face" but only issues a device wake when `active_override == schedule` — otherwise the new scheduled face becomes the state Now-Playing restores into.

## Further docs

- `docs/architecture.md` — component + data-flow diagram.
- `docs/deploy.md` — SSH setup, deploy command, rollback procedure.
- `docs/troubleshooting.md` — common failure modes.
- `docs/sleep-strategy.md` — the sleep-strategy helper defaults and rationale.
