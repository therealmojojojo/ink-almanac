# Troubleshooting

## Deploy failures

**SSH connection fails.** Check (in order):

1. VM reachable: `ping homeassistant.local`
2. Add-on running: HA UI → Settings → Add-ons → Advanced SSH & Web Terminal → Running
3. Key in add-on config: matches `cat ~/.ssh/id_ed25519.pub`
4. Add-on port matches `HA_SSH_PORT` (default 2222)

**`ha core check` fails after rsync.** Undo is safe:
`ssh … "rm /config/custom/inkplate/<offending-file> && ha core reload"`

## Entities not appearing

**`sensor.${PLACE_A_SLUG}_temperature_c` is `unavailable`.** Means the primary weather
entity failed to return a temperature AND the fallback also failed. Check
`weather.${PLACE_A_SLUG}_primary` and `weather.${PLACE_A_SLUG}_fallback` in the HA UI.

**`sensor.kitchen_temperature` is `unknown`.** The template sensor points at a
placeholder source (`sensor.kitchen_esp_temperature`). Edit
`ha/sensors/kitchen_climate.yaml` to point at the operator's real sensor
entity_id, redeploy.

**`sensor.news_digi24` missing.** The generator hasn't run. `deploy.sh` runs it
on every deploy, but you can force it: `python3 ha/scripts/generate_news_sensors.py`.

## Automations not firing

**Schedule automations update the helper but don't wake the device.** Check
`input_text.inkplate_active_override` — if it's not `schedule`, a higher-
precedence override is active. This is by design; see `architecture.md`.

**Sunday pairings automation fails with SSH errors.** Verify
`/config/.ssh/id_ed25519` exists on the VM and is authorized on the Mac host.

**Poetic-weather-line cache file stale.** Check HA logs: `tail -f /config/home-assistant.log | grep poetic_weather`. Common causes:

- `ANTHROPIC_API_KEY` missing → falls back to pool (intended)
- Hourly automation condition wrong (only runs 21:00–07:00)

## Low-battery flood

If you're getting notifications every few minutes, the 4-hour throttle is
working off `automation.last_triggered`, which resets on HA restart. If you
restarted HA mid-alert, this is expected. Otherwise verify the helper is
retained (it's an automation attribute, not a helper).

## Stale renderer inputs

The renderer serves from `renderer/inputs/*.json`. If a face looks frozen
in time (wrong clock, old weather), a publisher isn't firing.

Quick check on the Mac:

```bash
stat -f "%Sm  %N" ${INKPLATE_REPO}/renderer/inputs/*.json
```

Every file should be within the last minute or two (clock) or the last
state-change of its source sensor. Then check each path:

1. **`input_boolean.inkplate_publisher_enabled`** must be `on` — this is
   the master kill-switch for all five publishers.
2. **`renderer_input_auth_header`** and the five `renderer_publish_*_url`
   entries must exist in `ha/secrets.yaml`. Missing values log a startup
   warning; the publishers silently no-op.
3. **Renderer reachable** — `curl http://<renderer_host>:<renderer_port>/healthz`
   from the HAOS VM.
4. **rest_command fired but returned non-2xx** — tail HA logs for
   `rest_command` lines. 401/403 = wrong token; 404 = wrong `:name` in
   URL; 413 = body too large (>256 KB); 500 = filesystem write failed on
   the renderer.

To force a republish of all inputs without waiting for triggers, restart
HA (the `homeassistant: event: start` trigger re-publishes every input).

## MQTT topics

Use the Mosquitto add-on UI or `mosquitto_sub -h localhost -t 'inkplate/#' -v`
on the VM to inspect traffic. Retained messages (`active_mode`, `sleep_strategy`,
`state/device`) should persist across broker restarts; non-retained (`wake`,
`state/gesture`) only appear live.

## Drift from in-VM edits

The deploy is authoritative; in-VM edits are clobbered by the next deploy.
If you made an intentional in-VM change, copy it back into `ha/` before
deploying.
