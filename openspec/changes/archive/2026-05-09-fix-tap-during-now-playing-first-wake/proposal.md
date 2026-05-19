# Fix tap-during-now-playing — first wake confirms now-playing, subsequent taps peek to weather

> **Status — 2026-05-09**: live diagnosis on the operator's device, design agreed in conversation, implementation in this change directory.

## Why

`ha/automations/gesture_override.yaml`'s `inkplate_gesture_tap_now_playing_peek` handler treats every tap during a now-playing session as a peek-to-tier-main (gallery in midday/evening, summary in morning). That model breaks the most common operator flow:

1. Music starts → HA flips `override = now_playing` and publishes retained `active_mode = now-playing`. Wake pulse is best-effort and is lost when the device is mid-sleep.
2. Operator double-taps to wake the device. The expectation is that the device wakes and draws the now-playing face — that is the entire purpose of this tap.
3. Current code: HA's tap handler intercepts and publishes `gesture_response = gallery` and `active_mode = gallery`. The device wakes and draws **gallery** instead of now-playing.

Live on 2026-05-09, observed:

```
13:30:07Z  device timer-Full wake, drew weather (race-loss vs the alternation tick's gallery publish)
13:36:10Z  Sonos starts → override = now_playing, active_mode = now-playing retained
           wake pulse fires; device asleep; lost
13:42:26Z  user double-tap #1 → tap_now_playing_peek fires → publishes gallery
           device wakes, draws GALLERY (user expected now-playing)
13:42:53Z  user double-tap #2 → mode: restart re-fires the same peek → publishes gallery
           device wakes, redraws GALLERY (user saw "refresh, no change")
```

Operator's stated intent (after spec-silence on this case):

- **First** wake-tap of a now-playing session = "wake the device to show what's playing." Draw now-playing.
- **Subsequent** taps (screen already on now-playing) = "peek away from music for 60 s." Peek target is **weather**, not tier-main. Auto-revert at 60 s.
- **Tap during a peek** = cancel the peek, return to now-playing immediately. (i.e. tap to peek, tap again to come back.)

The peek-target change (tier-main → weather) reflects the actual ambient-glance use case: while listening to music, the operator wants to know the weather, not see today's gallery item.

## What Changes

### A. Two automations replace one

`ha/automations/gesture_override.yaml`:

1. **`inkplate_gesture_tap_now_playing_first_wake`** (new). Triggers on the same single+double gesture topic. Conditions: `override == now_playing`, quiet-hours guard, **and `sensor.inkplate_commanded_face != 'now-playing'`**. Action: a single non-retained publish of `inkplate/command/gesture_response = now-playing`. No `active_mode` publish (already retained). No wake pulse (the tap already woke the device). No delay or revert.

2. **`inkplate_gesture_tap_now_playing_peek`** (modified, not new). Add condition `sensor.inkplate_commanded_face == 'now-playing'`. Replace `peek_face` from the time-of-day branch to a literal `weather`. Otherwise unchanged: 60 s `mode: restart` peek, then publish `active_mode = now-playing` retained + wake pulse.

The mirror sensor (deployed 2026-05-08) reflects the face the device most recently *drew*. That makes it the natural discriminator: if the screen isn't on now-playing, this tap is the wake-up tap. If it is, this tap is a navigate-away peek.

### B. Tap-during-peek behaviour

Falls out of (A) for free: while peeking, mirror = `weather`. A new tap fires the first-wake handler (because `mirror != 'now-playing'`), which publishes `gesture_response = now-playing`. The device draws now-playing immediately. The peek's 60 s `mode: restart` timer is still running but its eventual revert publishes `active_mode = now-playing` — already retained, no-op.

### C. Spec change

`openspec/specs/now-playing-override/spec.md`: ADD a Requirement "Tap interaction during now-playing" with three scenarios (first wake, subsequent peek, tap during peek). The spec was silent on this case before — that silence was how the wrong implementation slipped in.

The pre-existing precedence-stack table (lines 82–101) still references legacy "single-tap Weather peek (5-min window)" and "double-tap Summary/Gallery toggle" overrides that no longer exist in the implementation. **Out of scope** for this change — flagged for a separate cleanup. Its presence does not block this change; it's noise rather than contradiction.

### D. Operator-facing docs

`ha/README.md` "Gesture handler" section: replace the one-liner about taps during now_playing with a two-line description matching the new behaviour.

## Impact

- **Behaviour change, operator-visible.** The first tap during music now lands on now-playing as intended. Subsequent taps peek to weather (not gallery). Operators who previously relied on the tap-to-gallery side effect lose that capability — but per discussion that side effect was unwanted.
- **Firmware unchanged.** This is HA-side only.
- **Risk.** Low. The discriminator is the mirror sensor; on cold boot or after the device has never published, mirror is unavailable, the `!= 'now-playing'` condition is true (None != 'now-playing'), and the first-wake path runs. That is the correct behaviour for cold boot.
- **Testability.** Live verification via the operator's device — covered by tasks 4.x.
