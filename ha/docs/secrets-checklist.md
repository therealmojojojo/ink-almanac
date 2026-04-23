# Secrets checklist

Required entries in `ha/secrets.yaml` (copy from `ha/secrets.yaml.example`).

| Key | Required when | Source |
|---|---|---|
| `openweathermap_api_key` | weather fallback | https://openweathermap.org/api — free tier sufficient |
| `${PLACE_A_SLUG}_latitude` / `_longitude` / `_elevation` | always | operator |
| `${PLACE_B_SLUG}_latitude` / `_longitude` / `_elevation` | always | operator |
| `anthropic_api_key` | `provider: claude` in poetic_weather_line.yaml | https://console.anthropic.com |
| `renderer_host` / `renderer_port` | always | operator LAN |
| `renderer_input_auth_header` | always | pre-composed `"Bearer <token>"`; matching bare token goes in the renderer's `RENDERER_INPUT_TOKEN` env var. Generate: `python3 -c "import secrets; print(secrets.token_urlsafe(32))"` |

The per-endpoint publisher URLs are **not** secrets — they're LAN coordinates.
They live in `ha/integrations/rest_commands.yaml` alongside the command
definitions. Edit there if the renderer host/port ever changes.
| `mqtt_broker_host` / `mqtt_broker_port` | always | Mosquitto add-on — normally `homeassistant.local:1883` |
| `operator_notify_service` | low-battery + pairings notifications | HA mobile app → `notify.mobile_app_<device_id>` (check Developer Tools → Services) |

Other credentials that don't go through `secrets.yaml`:

- **Sonos**: handled by HA's native integration (OAuth/local discovery — no key).
- **HN**: unauthenticated public API.
- **MET.no**: unauthenticated (requires User-Agent; HA sets this).
- **Mosquitto user for the device**: configured inside the add-on, not in `secrets.yaml`. Matching credentials live in `firmware/include/secrets.h` (see `secrets.h.example`).
