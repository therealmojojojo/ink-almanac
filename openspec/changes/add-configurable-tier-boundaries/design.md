# Design — Configurable tier boundaries

## Goal

Move the four schedule tier boundaries (Morning / Midday / Evening / Night start times) from compile-time constants in `firmware/src/wake.cpp` and Jinja literals in HA YAML to runtime-configurable HA helpers, propagated to the firmware via a retained MQTT topic. Eliminate the duplication; make the schedule operator-tunable.

## Non-goals

- Per-tier cadences (`{full=15, poll=3, partial=1}` etc.). They are tied to hardware behavior — panel refresh time, partial-pulse cost, post-Full clock cleanup timing — and shifting them silently degrades battery or visual quality. They stay `constexpr`.
- Alternation period (15/30/15 min) or tier→main-face mapping (Morning=Summary, Midday/Evening=Gallery). These are HA-only, already in YAML, and changing them is a YAML edit, not a config-knob ask.
- Any UI for editing boundaries beyond the standard HA `input_datetime` card.
- Per-day-of-week schedules (e.g., "weekend Gallery starts later"). Out of scope; would be a separate proposal.

## MQTT contract

New retained topic: `inkplate/command/tier_boundaries`.

Payload (JSON), all values local-time `HH:MM`:

```json
{
  "morning_start": "06:30",
  "midday_start":  "10:00",
  "evening_start": "17:00",
  "night_start":   "22:00"
}
```

Payload constraints (enforced HA-side before publish, firmware-side on read):

1. All four fields present and parseable as `HH:MM`.
2. Strictly increasing in clock-time order: `morning_start < midday_start < evening_start < night_start`.
3. Each tier ≥ 30 minutes wide. (Defends against an operator inadvertently zeroing out a tier and confusing both the wake planner and the alternation engine.)
4. Night tier wraps midnight by construction: `night_start` to `morning_start` of next day. This is implicit, not encoded.

Payloads failing any constraint:

- **HA side**: the publisher automation refuses to publish; logs a warning to the HA system log; the previously-published valid payload remains retained.
- **Firmware side**: `wake::loadTierBoundaries` parses, validates, and on any failure leaves the cached values untouched and logs `"tier-boundaries parse failed payload='...'"`. If the cache was never populated (cold boot), `tierFor()` uses compile-time defaults.

## Firmware changes

### RTC field

```cpp
struct Persisted {
  // ... existing fields ...
  uint16_t morning_start_min;   // 0 = unset → use defaults
  uint16_t midday_start_min;
  uint16_t evening_start_min;
  uint16_t night_start_min;
};
```

`uint16_t` because minute-of-day fits in 11 bits and we already use `uint16_t` for `clock_zone_font_size`. Total RTC growth: 8 bytes; ample headroom.

### Reader

```cpp
// firmware/src/wake.cpp
namespace fw::wake {

struct TierBoundaries {
  int morning_min;  // local minute-of-day
  int midday_min;
  int evening_min;
  int night_min;
};

constexpr TierBoundaries kDefaultBoundaries = {390, 600, 1020, 1320};

TierBoundaries effectiveBoundaries() {
  const auto& p = persisted();
  if (p.morning_start_min == 0) return kDefaultBoundaries;  // sentinel for "unset"
  return {p.morning_start_min, p.midday_start_min,
          p.evening_start_min, p.night_start_min};
}

}  // namespace fw::wake
```

`tierFor(int min_of_day)` is rewritten to consult `effectiveBoundaries()` instead of literals. Stays a pure function — no allocation, no caching beyond the RTC field.

### MQTT subscriber

`main_loop.cpp` already reads retained `inkplate/command/sleep_strategy` on every wake (via `mqttReadRetained`). Extend the same step to also read `inkplate/command/tier_boundaries`, parse, validate, store. Same failure semantics as the sleep-strategy path: parse failure logs and skips, never crashes.

The boundaries are read from MQTT on every wake (cheap — single MQTT round-trip, payload <100 bytes), but only applied to the persisted fields if validation passes. This mirrors the sleep-strategy pattern and avoids any "stale RTC value, fresh broker value" divergence.

### Test surface

New tests in `firmware/test/scenarios/schedule_tests.cpp`:

- `tierFor with default cache → matches existing behavior`: regression guard.
- `tierFor with shifted Morning start → tier classification changes`: cache `{420, 600, 1020, 1320}` (Morning starts 07:00), assert min 405 classifies as Night, min 425 as Morning.
- `Malformed cache (zero sentinel) → falls back to defaults`: ensures the cold-boot path is robust.

New host-test fixture (`firmware/test/...`) for the MQTT read path: simulate a tier-boundaries payload, run a tick, assert the persisted fields are updated.

## HA changes

### Helpers (`ha/integrations/helpers.yaml`)

```yaml
input_datetime:
  inkplate_morning_start:
    name: "Inkplate Morning tier start"
    has_date: false
    has_time: true
    initial: "06:30"
  inkplate_midday_start:
    name: "Inkplate Midday tier start"
    has_date: false
    has_time: true
    initial: "10:00"
  inkplate_evening_start:
    name: "Inkplate Evening tier start"
    has_date: false
    has_time: true
    initial: "17:00"
  inkplate_night_start:
    name: "Inkplate Night tier start"
    has_date: false
    has_time: true
    initial: "22:00"
```

### Publisher automation

Mirror `ha/automations/sleep_strategy.yaml`'s shape. Triggers:

- Any of the four `input_datetime.inkplate_*_start` state changes
- HA start (defensive against broker losing the retained payload)

Action: build payload, run validator template, publish to `inkplate/command/tier_boundaries` retained. On validator failure, write to the HA system log and notify the operator via the existing `ha/automations/low_battery.yaml` notify channel pattern.

Validator template (Jinja, runs in the publisher action):

```jinja
{% set m = states('input_datetime.inkplate_morning_start') %}
{% set d = states('input_datetime.inkplate_midday_start') %}
{% set e = states('input_datetime.inkplate_evening_start') %}
{% set n = states('input_datetime.inkplate_night_start') %}
{% set m_min = (m.split(':')[0] | int) * 60 + (m.split(':')[1] | int) %}
{% set d_min = (d.split(':')[0] | int) * 60 + (d.split(':')[1] | int) %}
{% set e_min = (e.split(':')[0] | int) * 60 + (e.split(':')[1] | int) %}
{% set n_min = (n.split(':')[0] | int) * 60 + (n.split(':')[1] | int) %}
{% set monotone = m_min < d_min and d_min < e_min and e_min < n_min %}
{% set min_width = 30 %}
{% set widths_ok = (d_min - m_min) >= min_width
                  and (e_min - d_min) >= min_width
                  and (n_min - e_min) >= min_width %}
{{ monotone and widths_ok }}
```

### Schedule and gesture-override Jinja

`schedule.yaml` and `gesture_override.yaml` currently inline tier boundaries:

```jinja
{% if m < 10*60 %}{% set tier_start = 6*60 + 30 %}
```

Rewrite as:

```jinja
{% set t_morning = states('input_datetime.inkplate_morning_start') %}
{% set m_morning = (t_morning.split(':')[0] | int) * 60 + (t_morning.split(':')[1] | int) %}
{% if m < m_midday %}
  {% set tier_start = m_morning %}
```

Verbose, but no helper macros are shared across HA's flat automation list (already noted in `gesture_override.yaml:88-89`). Acceptable cost for the single source of truth.

## Failure modes and recovery

| Failure | Detection | Fallback |
| --- | --- | --- |
| Operator sets non-monotone boundaries | HA validator template returns false | publisher refuses to publish; previous retained payload remains; HA log warning + notify |
| Operator sets a tier <30 min wide | same | same |
| Helper deleted from UI | publisher template fails | publisher refuses to publish; previous retained payload remains |
| Broker loses retained payload (e.g. broker reset, no message persistence) | next firmware wake reads empty | firmware sees no `tier_boundaries` topic → keeps existing RTC values; if cold boot too, `tierFor` falls back to compile-time defaults |
| Firmware OTA wipes RTC | `Persisted` zero-init → sentinel | `tierFor` uses defaults until next MQTT read at next wake |
| Payload parse failure (truncated, malformed JSON) | firmware parser returns false | RTC fields untouched; FW_LOG records the failure; `tierFor` continues with last-good values (or defaults) |

The system never crashes or stops scheduling because of a bad config. Worst case: the schedule reverts to compile-time defaults, which are the same values the device runs today.

## Open questions

1. **Should the publisher run the firmware's "rebuild scheduled_face" path immediately after a boundary change?** A boundary change while the panel is in Midday could mean the current minute is now in Morning; the alternation engine would compute a different `scheduled_face` next tick. Today the schedule.yaml tick runs every 15 min so the operator sees the change within 15 min. Acceptable, but could be made instant by firing a synthetic schedule-tick from the publisher action. Lean: defer; not worth the extra automation surface for a knob that turns rarely.

2. **Should `night_start` and the wrap-around to `morning_start` be one helper or two?** Two is symmetric with the others and matches HA's input_datetime model. Worth keeping as proposed unless an operator finds it confusing.

3. **Migration**: do we need a one-shot helper-initialization automation that publishes the default boundaries on first install? Probably yes — without it, a fresh HA setup would have no retained payload until the operator manually nudges a helper. Trivial to add as a `homeassistant.start` trigger that publishes if the topic is currently absent.
