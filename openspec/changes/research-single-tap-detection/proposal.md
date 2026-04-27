# Research: reliable single-tap detection on the wire-tied frame mount

> **Status — 2026-04-27**: research only. No implementation until findings are reviewed and a path is selected. The current "double-tap-or-nothing" behavior remains shipped.

## Why

On the operator's wire-tied frame mount the LSM6DSO's hardware tap classifier produces a binary outcome:

- **Below threshold** → soft taps don't register at all (no INT1 wake, no event)
- **Above threshold** → every tap latches `DOUBLE_TAP`, never `SINGLE_TAP`

Confirmed empirically 2026-04-27 by serial-monitor capture: every measured `TAP_SRC` after a firm tap reads `0x59` or `0x5A` — bit 6 (`TAP_IA`) and bit 4 (`DOUBLE_TAP`) both set, bit 5 (`SINGLE_TAP`) never set, axis bits indicating the latched-Y artefact rather than Z.

Why: the wire-tied frame *rings* on impact. The initial finger shock plus the frame rebound (arriving within ~150 ms) both clear the IMU's slope-HPF threshold within the 350 ms `kDoubleTapWindowMs`, so the classifier's second-shock detector fires every time. Tightening `kTapThreshold` from its current floor (1, the IMU minimum) is not possible — the chip rejects lower values.

Today this is masked by HA collapsing both single and double to the same intent (per `ha/automations/gesture_override.yaml:11-16`), so the operator sees "tap = flip alternation" regardless. But two latent costs remain:

1. **Visual ack ambiguity** — every tap renders 2 dots. The single-vs-double distinction the firmware paints is operator-readable diagnostic but not actuator-meaningful, and the operator cannot tell whether a particular tap was firmly intended (would-be-double) or accidentally registered (would-be-single) by the chip's classifier.
2. **No future room for distinct gestures** — if the operator ever wants single-tap and double-tap to drive different operations (e.g., next face vs. peek-to-now-playing), the current mount + classifier combination cannot support it.

This research change scopes the *investigation* of whether a software-only path can reliably distinguish single-tap from double-tap on this physical mount, and what trade-offs each approach would impose.

## What this change is — and isn't

**Is**: a structured investigation. The deliverable is a decision document — which path to pursue, with measured data backing the choice, plus a follow-up implementation proposal authored after the findings settle.

**Isn't**: an implementation proposal. No firmware code changes, no specs delta to ratify, no tasks list of "ship X". Tasks here are research tasks (measure, prototype, decide).

The current shipped behavior (every tap → DOUBLE → HA flips alternation) is correct and stable. Don't disrupt it during the investigation.

## What the investigation must answer

1. **Is the frame-rebound period observable and characterisable?** Capture raw accelerometer time-series across multiple tap impacts; identify whether the rebound arrives at a consistent delay (e.g., ~120-180 ms) and amplitude (typically lower than the initial shock).
2. **Can the LSM6DSO's `INT_DUR2.DUR` window be tightened to fall *between* the initial shock and the frame rebound?** If yes, what window value, and what is the human-side cost (does it preclude deliberate double-tap)?
3. **Can the LSM6DSO's `WAKE_UP_THS` / `WAKE_UP_DUR` registers detect taps the tap-classifier misses?** Establish noise floor in the operator's kitchen environment (HVAC, fridge compressor, footsteps); measure false-positive rate.
4. **Can a firmware-side classifier on raw accel data outperform the hardware classifier on this mount?** Measure: latency added to wake path, battery impact, accuracy on a tap-test corpus.
5. **What is the operator's reliability bar?** Define "single tap works" quantitatively (e.g., 95% of intentional single-finger taps register as `single`, false-positive wake rate <1/hour). The investigation cannot conclude without an explicit success criterion.

## Capabilities

### Modified Capabilities

None during the research phase. If the investigation concludes a viable path, a follow-up *implementation* change will modify `device-firmware` (the IMU init + `drainPendingTap` decode), and possibly `dashboard-faces` if the visual-ack contract changes.

### New Capabilities

None.

## Impact

- **Documentation produced**: this proposal + the design exploration in `design.md` + the investigation log under tasks. Future readers can find the rationale for whichever decision lands without re-running the research.
- **Time investment**: estimated 4-8 hours of focused investigation (oscilloscope or raw-accel capture, register experiments, prototype). Not a sprint; can land in a week of evening work.
- **Hardware-side option (rigid IMU mount or external piezo) is documented but explicitly out of scope** for this research. It exists in design.md as a fall-back if all software paths fail their reliability bars.
- **No risk to current device behavior**: investigation runs against a development device or via raw-accel sampling that doesn't disrupt the shipped tap pipeline.
