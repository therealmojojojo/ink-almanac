# HA integrations — spec delta

## ADDED Requirements

### Requirement: Raw PWR_GOOD telemetry sensor

HA SHALL expose `sensor.inkplate_device_epd_pwr_good_raw` reading
`value_json.epd_pg_raw` from retained `inkplate/state/device`. The
value is a hex string (e.g. `"0x00"`, `"0xA0"`, `"0xFA"`, `"0xFF"`)
representing the TPS65186 PWR_GOOD register byte at the end of the
most recent Full wake. (The entity_id is HA's slugification of the
sensor's friendly name "Inkplate device EPD PWR_GOOD raw"; YAML-
configured MQTT entities cannot pin `object_id`.)

#### Scenario: Operator inspects byte after a freeze

- **WHEN** the operator sees `binary_sensor.inkplate_device_epd_power_good
  = on` (problem present) and opens
  `sensor.inkplate_device_epd_pwr_good_raw`
- **THEN** the displayed value identifies the wedge class (`0xA0` =
  partial-power, `0xFF` = chip silent, etc.) without needing to flash
  the USB diagnostic.

### Requirement: Predictive unclean-down warning

HA SHALL expose `binary_sensor.inkplate_device_epd_down_clean` mirroring
`value_json.epd_down_clean`, with `device_class: problem` and
`payload_on: "false"` / `payload_off: "true"` (so `on` means
"un-clean" = problem present, matching the existing `epd_power_good`
sensor convention).

An automation `inkplate_epd_down_unclean_warning` SHALL fire when
`binary_sensor.inkplate_device_epd_down_clean` is `on` for
`00:31:00` (one Midday Full-cycle window — same debounce as the
existing pwrgood alert). The notification SHALL share the same target
service as `inkplate_epd_pwrgood_alert` and be throttled to no more
than once per 4 hours via the same template-condition idiom.

The warning is *predictive*: it fires before the panel actually
freezes, giving the operator time to react. This is distinct from
`inkplate_epd_pwrgood_alert`, which fires *after* the freeze has begun.
Both alerts can fire on the same incident — the predictive warning
typically lands ~15-30 min before the freeze alert if telemetry is
working correctly.

#### Scenario: Predictive warning precedes an actual freeze

- **WHEN** wake N publishes `epd_down_clean: false` (rails didn't drain
  cleanly this cycle), wake N+1 also publishes `epd_down_clean: false`
  (31 min later, same condition recurs), and the predictive automation
  fires
- **THEN** the operator receives a notification "panel may freeze on
  the next wake — rails didn't drain cleanly." If wake N+2 then fails
  `ensurePanelPower`, the existing `inkplate_epd_pwrgood_alert` also
  fires 31 min later (per its debounce); both alerts route to the same
  notify service.

#### Scenario: Single unclean-down event clears

- **WHEN** wake N publishes `epd_down_clean: false` but wake N+1
  publishes `epd_down_clean: true` (transient that cleared)
- **THEN** the predictive warning does not fire (the 31-min `for:`
  condition is broken on the recovery wake), no notification is sent.
