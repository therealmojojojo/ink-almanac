# Design — Fix the IMU gesture grace-window race

## The race

Sequence diagram of a tap under the pre-fix firmware:

```
Operator   Device                      Broker                 HA
  │ tap     │                             │                    │
  │────────►│                             │                    │
  │         │ ext0 wake from deep sleep   │                    │
  │         │ … wifi up, mqtt up …        │                    │
  │         │ publish state/gesture ─────►│                    │
  │         │                             │ ─── deliver ──────►│
  │         │ subscribe active_mode ─────►│                    │
  │         │                             │ ◄── retained "summary" replay (~30 ms)
  │         │ ◄── "summary" — captured!   │                    │
  │         │ unsubscribe ───────────────►│                    │
  │         │ exit grace window           │                    │
  │         │                             │  HA evaluates ←────│
  │         │                             │  publish "weather"◄│
  │         │ resolve active = summary    │                    │
  │         │ render summary face         │                    │
```

The retained `active_mode = "summary"` replay arrives ~30 ms after subscribe. The wait's `while (!captured_)` loop captures it and exits. HA's fresh `"weather"` publish lands at the broker ~150 ms later but the device has already unsubscribed. The same is true at QoS 0 with no retained replay if HA happens to publish *after* the wait deadline — but the dominant failure mode in steady state is the retained-replay race because `active_mode` is *always* retained and *always* set to whatever face is current.

## Why not "fix the wait"

Considered fix: change `waitImpl` to spin the full `timeout_ms` and return the *last* captured payload, so HA's late `"weather"` overwrites the early `"summary"`.

Rejected on architectural grounds:

1. **State-vs-event conflation**. `active_mode` is a state topic, queried by the schedule planner, by Poll wakes, by restart recovery. Every other consumer wants the broker's "current value on subscribe" semantics. Repurposing the same topic as an event channel via a "wait full window, last writer wins" rule on the firmware side would force every other consumer to reason about whether they're getting state-or-event semantics, and would make the firmware's tap path the odd one out.

2. **2-second wait every IMU wake**. With the wait-full-window fix there's no safe way to short-circuit on first message because the first message is *always* the retained replay. Battery-relevant: 2 s extra awake at ~80 mA is ~45 µAh per tap. Small per tap, but the constraint shapes future code: any future feature that wants a similar "ack-then-respond" round-trip would inherit the same "always wait full window" cost.

3. **Cross-publisher hazard**. Anything else that writes `active_mode` during the 2 s window (operator dashboard, an automation tick straddling a minute boundary) silently overrides the gesture response. Today nothing else writes during a 2 s window; a year from now someone adds an automation and the bug reappears, hard to attribute.

4. **Race not fully eliminated**. If HA's `"weather"` and the broker's retained `"summary"` arrive within the same `mqtt_.loop()` callback batch, ordering is undefined at QoS 0. Rare on LAN, but the protocol contract no longer guarantees correctness — only LAN timing does.

The "fix the wait" approach patches the symptom; the topic-separation approach makes the protocol contract explicit and keeps each topic's semantics single-purpose.

## Why a separate event topic

`inkplate/command/gesture_response`:

- **Non-retained by contract**. The HA-side automation publishes with `retain: false`. No broker replay on subscribe.
- **Empty at idle**. No-one is responsible for "clearing" it; it's an event channel, not a state channel.
- **Same value-space as `active_mode`** (face name as plain string). Re-uses the firmware's `parseModePayload` without modification.
- **Listened to only inside the IMU branch**. The Poll/Full branches still consult `active_mode` retained — that's the right shape for them (cold-boot recovery, sleep-window updates).

The separation also lets the firmware safely short-circuit the wait on first received message: there's no retained value to confuse it, so the first push *is* HA's response. Battery cost: zero in the common case (HA responds in tens of ms; wait exits immediately).

## Timeout fallback

When the wait expires with no message, two interpretations are reasonable:

a) **HA bailed** (gesture handler condition didn't match — e.g., quiet hours suppressed the tap). The device should keep the persisted current mode and not change face.

b) **HA was slow** (broker delay, HA load, network blip). The device's best guess is whatever HA last published on `active_mode` retained. If that differs from the persisted current mode (because a /15 alternation tick fired during sleep), respecting it gives the user the freshest face HA has decided on.

(b) requires one extra `mqttReadRetained` on `active_mode`, ~50 ms on LAN. (a) costs nothing extra. Today's racy code accidentally implements (b), so users have implicitly come to expect "tap during a slept-through alternation gives me the new face". Preserving that means the spec stays a behavioral superset of the pre-fix code.

Decision: **fall back to `resolveActiveMode` on timeout**. Reads cleanly:

```cpp
if (reason == wake::Reason::IMU && tap != fw::gestures::TapKind::None && mqtt) {
    h.transport.mqttPublish(kTopicGesture, ..., /*retained=*/false);

    auto payload = h.transport.mqttWaitForMessage(
        fw::config::kTopicGestureResponse, fw::config::kGestureGraceMs);
    if (!payload.empty()) {
        auto m = parseModePayload(payload);
        if (m != fw::modes::Mode::Unknown) active = m;
    } else {
        // HA didn't respond on the event channel within the grace window.
        // Fall back to the retained state channel — captures any sleep-
        // window alternation update without making this branch racy
        // again (the retained read is a separate semantic from the
        // grace-window wait, even if it lands on the same topic).
        active = resolveActiveMode(h.transport, local_hour);
    }
}
```

This is the only code-path divergence from the strict "subscribe to event topic only" model. The reason is honesty: users have come to depend on the side-effect benefit of the racy code, and the cost of preserving it is one cheap retained read.

## Test-harness model

`MockTransport::mqttWaitForMessage` previously returned only retained values, ignoring `timeout_ms`. The publish hook fires synchronously inside `mqttPublish`, so by the time `mqttWaitForMessage` runs, the hook has already pushed whatever HA-simulation traffic the test wants. The mock just needs to remember that traffic.

Two changes:

1. `mqttPublish` stores the most recent non-retained payload per topic into a `pending_push_` map (in addition to the existing `retained_` map for retained publishes).
2. `mqttWaitForMessage` returns the retained value if present (mimics broker replay on subscribe), otherwise drains and returns `pending_push_[topic]` if present, otherwise empty.

The drain-on-read makes a second wait without a fresh push return empty — modelling a real wait that times out. Tests can chain `mqttWaitForMessage` calls without the first call's "response" leaking into the second.

This model is *additive*: existing tests using retained publishes (`now_playing_track_tests`, `session_override_tests`, etc.) see no behavior change because they don't go through the `pending_push_` path.

## HA automation actions

Both gesture automations gain one new `mqtt.publish` ahead of the existing `active_mode` publish:

```yaml
- service: mqtt.publish
  data:
    topic: inkplate/command/gesture_response
    payload: "{{ flip_face | trim }}"
    retain: false
- service: mqtt.publish              # ← unchanged
  data:
    topic: inkplate/command/active_mode
    payload: "{{ flip_face | trim }}"
    retain: true
- service: mqtt.publish              # ← unchanged
  data:
    topic: inkplate/command/wake
    payload: ""
    retain: false
```

Order matters only weakly: the device's grace window is 2 s, the two publishes complete within tens of ms on a healthy HA. Putting `gesture_response` first reduces tail-latency for the in-flight wake; putting `active_mode` first ensures any concurrent Poll wake sees the new state immediately. We pick `gesture_response` first because the in-flight IMU wake is the time-critical consumer.

## Deployment order

HA first, then firmware. Reasons:

- **HA-first** is safe: HA publishes to a topic no one subscribes to → no-op. The current firmware (still listening on `active_mode`) keeps doing the racy thing — same end-user experience as today.
- **Firmware-first** breaks taps: the new firmware listens on `gesture_response` which old HA doesn't publish → 2 s timeout → fallback to `resolveActiveMode` which reads the *same* retained `active_mode` the firmware was reading anyway. End-user experience: same as today (still racy, but no worse).

So either order is acceptable; HA-first is preferred because it makes the new path live the moment the firmware boots after OTA.

## Out of scope

- **Visual changes**. The ack glyph, partial-update path, and full-refresh on tap are unchanged.
- **Tap classification**. Single vs double remains an HA-side concern (and is currently collapsed; see `research-single-tap-detection` for the longer-term plan).
- **Battery measurement**. The wait's 2 s ceiling is unchanged; the ~50 ms timeout-fallback retained read is well below noise.
- **Event-channel reuse**. Future "HA, react before I sleep" patterns (OTA ack, weather-peek button) could reuse the gesture_response topic or follow the same shape with a sibling topic. Not designed in this change.
