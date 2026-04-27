# Sleep-strategy helpers

Defaults shipped in `integrations/helpers.yaml` and republished to the
retained MQTT topic `inkplate/command/sleep_strategy` by
`automations/sleep_strategy.yaml` on any helper change.

| Helper | Default | Range | Rationale |
|---|---|---|---|
| `input_datetime.inkplate_sonos_active_start` | `07:00` | — | Sonos fast-path wakes start; aligned with typical morning kitchen activity. Earlier wastes battery; later misses early coffee. |
| `input_datetime.inkplate_sonos_active_end` | `20:00` | — | Sonos fast-path wakes end; after this Now-Playing still works but cadence returns to per-mode timer. |
| `input_datetime.inkplate_quiet_start` | `00:00` | — | Start of the hard-quiet window — no wakes at all. Room dark, no one cooking. |
| `input_datetime.inkplate_quiet_end` | `05:00` | — | End of the hard-quiet window; Night mode resumes its hourly cadence. |
| `input_number.inkplate_fast_path_interval_seconds` | `180` | `60–600` | How often the device checks for Now-Playing activation during Sonos active hours. The firmware's `kSonosFastPathSec` is now 60 s (daytime mode timers also 60 s, so the fast path is mostly redundant under the current schedule). The HA helper still defaults to 180 s for legacy compatibility — overrides via this helper republish to MQTT for the device to read on its next wake, but the planner's per-tier cadence wins for routine wakes. |

The device reads this topic on every wake via `mqttReadRetained()`; HA changes
propagate on the device's next natural wake (no push needed). The `republish on
HA start` trigger guards against broker restarts losing the retained payload.
