# Design — Fix `resolveActiveMode` time-of-day fallback during MQTT hiccups

## How the bug manifests

`mqttReadRetained` (`firmware/src/hal/real/RealTransport.h::waitImpl`) is implemented as:

```cpp
std::string waitImpl(const std::string& topic, int timeout_ms) {
  captured_topic_ = topic;
  captured_payload_.clear();
  captured_ = false;
  mqtt_.subscribe(topic.c_str(), /*qos=*/0);
  uint32_t deadline = millis() + static_cast<uint32_t>(timeout_ms);
  while (millis() < deadline && !captured_) {
    mqtt_.loop();
    delay(5);
  }
  mqtt_.unsubscribe(topic.c_str());
  return captured_payload_;
}
```

`mqttReadRetained` calls `waitImpl(topic, 800)`. The broker normally delivers the retained value within ~50 ms of subscribe on LAN. On a marginal RSSI link (we saw -76 dBm in the live capture), MQTT TCP retransmits + WiFi retries can push delivery past 800 ms. When that happens, `captured_payload_` is still empty when the deadline hits, the call returns `""`, and the caller — `resolveActiveMode` — falls through to its time-of-day fallback.

The time-of-day fallback returns `Weather` for any local hour in `[10, 22)`. So at any time of normal-people activity, an empty read maps to Weather. That mode is then fed to `pathForMinute`'s mode-change-promotion logic, which sees `Weather != current_mode (= NowPlaying)` and promotes the Poll to a Full. The Full draws Weather, sets `current_mode = Weather`, and publishes `state/device.active_mode = weather`.

Then the next Poll's `mqttReadRetained` usually succeeds (the broker's retained value was always `now-playing`, the read just timed out the previous time). It sees `now-playing != Weather`, promotes to a Full, draws NowPlaying, sets `current_mode = NowPlaying`. Net cost: two extra Fulls per hiccup, with a brief Weather flash visible to the operator.

## Why time-of-day fallback ever existed

It's the right answer for **one specific scenario**: cold boot when HA hasn't yet populated `inkplate/command/active_mode`. The retained topic is genuinely empty, and the device needs *something* to draw. Time-of-day inference gives a reasonable default (Summary in the morning, Weather midday/evening, Night overnight) that approximately matches what the schedule will produce once HA catches up. Without that fallback, a fresh-flash device would either error-glyph or wedge until HA's first publish lands.

The `device-firmware` "Boot with network unreachable" scenario explicitly covers this case: WiFi down, no published topic, device falls back to time-of-day. That's still correct.

The bug is that `resolveActiveMode` doesn't distinguish "we have no idea, this is genuinely first boot" from "we know exactly what we drew last and the read just hiccupped."

## The fix

```cpp
fw::modes::Mode resolveActiveMode(hal::ITransport& mqtt, int hour) {
  auto payload = mqtt.mqttReadRetained(fw::config::kTopicActiveMode);
  if (!payload.empty()) {
    auto m = parseModePayload(payload);
    if (m != fw::modes::Mode::Unknown) return m;
  }
  if (wake::persisted().current_mode != fw::modes::Mode::Unknown) {
    return wake::persisted().current_mode;
  }
  return timeOfDayFallback(hour);
}
```

`wake::persisted().current_mode` is set to `Unknown` only at process-init in the host build, and at RTC-init on the device (RTC slow memory zeroes on power-up). After the first successful Full draw, `current_mode` is updated to the active mode (`firmware/src/main_loop.cpp:511`). So the new check correctly distinguishes:

- **Cold-boot pre-MQTT**: `current_mode == Unknown`, payload empty → time-of-day fallback. Same behavior as before.
- **Steady-state read failure**: `current_mode == <last drawn>`, payload empty → return `current_mode`. NEW behavior — replaces the buggy time-of-day call.
- **Steady-state read success**: payload non-empty → return parsed value. Same behavior as before.

## Why not just bump the timeout

Considered: change `mqttReadRetained` from 800 ms to 2000 ms. Pros: simpler one-line fix. Cons:

- Doesn't fix the root cause. A read can still time out (broker overload, WiFi outage during the read, etc.) — the bug just becomes rarer.
- Adds latency to *every* read in steady state (typical 50 ms now becomes occasionally up to 2000 ms when broker is slow). Battery cost.
- Asymmetric treatment of the same failure mode: short-window taps (`gesture_response`, `kGestureGraceMs = 2000`) can't extend; this only helps the read path.

The proper fix is to make the *fallback* logic correct. Bumping the timeout is a workaround.

## Why not return `Mode::Unknown` and let the caller decide

Considered: instead of returning `current_mode` on hiccup, return `Mode::Unknown` and let `tick()` skip the wake (no draw, no current_mode update, just go back to sleep).

Rejected because:

- The current `resolveActiveMode` contract is "always returns a renderable mode" — every caller assumes a real value.
- Skipping the wake doesn't help the Poll path's clock-tick partial draw (we'd lose the partial too).
- `current_mode` IS the right answer in this case: it's what's currently on the panel, and the Poll's job is "did anything change?" — empty read means "we don't know, no signal" → "no change" → keep current_mode → no promotion.

## Test coverage

`firmware/test/scenarios/main_loop_tests.cpp` already has an "HA silent" gesture test where the publish hook installs nothing — that previously asserted "current_mode is preserved through the IMU grace window." The same assertion should hold for non-IMU paths under the new fallback rule. We add one explicit test:

```cpp
TEST_CASE("active_mode fallback: empty retained read after first Full preserves current_mode") {
  // Cold-boot into Gallery so current_mode = Gallery.
  // Subsequent Timer wake with EMPTY active_mode retained:
  //   - With the bug: would resolve to Weather (time-of-day at 14h), promote
  //     to Full, draw Weather, set current_mode = Weather.
  //   - With the fix: should resolve to Gallery (preserved current_mode),
  //     no mode-change promotion, no extra Full.
  // Assertion: fullRefreshCount stays at 1 (the cold-boot Full).
}
```

The cold-boot scenario already passes (it relies on the time-of-day fallback when `current_mode == Unknown`); we just verify it still does.

## Out of scope

- `mqttReadRetained` timeout tuning. Separate concern; current 800 ms stays.
- `mqttWaitForMessage` (the gesture-response grace-window read) is unaffected — that path is non-retained and its 2 s timeout is intentional.
- WiFi RSSI improvement. The bug surfaces when RSSI is marginal, but the fix is correct under any signal strength; we don't need to address the RSSI separately.
