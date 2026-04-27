# Tasks — Single-tap detection research

These are *investigation* tasks, not implementation tasks. Each produces evidence that informs the decision; none ships behavior. The deliverable of this change is a follow-up implementation proposal authored after §5.

## 1. Define the success criterion

- [ ] 1.1 Operator commits to a numeric reliability bar for single-tap. Suggested defaults: ≥95% of intentional finger taps land as `SINGLE_TAP` within 1 s; ≤1 false-positive wake per hour over a 24-hour mounted dry run. Confirm or adjust.
- [ ] 1.2 Operator decides whether deliberate double-tap must remain a distinct gesture. If yes, eliminates Paths A and B; only C, D, E qualify. If no, all paths qualify and we sequence by cost.

## 2. Capture mount mechanics

- [ ] 2.1 Configure the LSM6DSO FIFO (or a debug build that streams raw accel via UART) to capture ~833 Hz Z-axis samples for 5-second windows around each tap
- [ ] 2.2 Capture 20 firm intentional taps, plot the time-series, identify the rebound's typical delay and amplitude ratio (rebound peak / initial peak). Produce a single annotated plot
- [ ] 2.3 Capture 20 attempts at "softest possible deliberate tap" (operator's natural light tap). Note how many register at all on the current `kTapThreshold = 1` config
- [ ] 2.4 Capture 1 hour of mounted background data (no taps) at idle. Identify environmental shocks: HVAC, fridge compressor cycle, footsteps near the mount, door slams. Note their amplitudes vs. the tap threshold
- [ ] 2.5 Save the raw captures into `firmware/research/single-tap/` (gitignored) so future investigators don't have to re-capture

## 3. Path A — DUR window tightening

- [ ] 3.1 Reconfigure `INT_DUR2.DUR` to a series of values: `15` (~1.15 s, baseline), `8` (~0.62 s), `4` (~0.31 s), `2` (~0.15 s), `1` (~0.077 s). For each, capture 20 firm taps and record the `TAP_SRC` distribution (single/double/none)
- [ ] 3.2 Identify the DUR value where `SINGLE_TAP` starts latching reliably (≥80% of taps). Record it
- [ ] 3.3 At that DUR value, attempt 20 deliberate double-taps (rapid two-finger taps). Measure how many latch as `DOUBLE_TAP`. If <50%, confirm Path A trades double-tap entirely; if ≥80%, Path A potentially preserves both — surprising, document carefully

## 4. Path B — WAKE_UP function

- [ ] 4.1 Add a debug build branch that replaces tap-classifier init with WAKE_UP init: set `WAKE_UP_THS` and `WAKE_UP_DUR` registers, route `WAKE_UP_INT` to INT1, change `drainPendingTap` to read `WAKE_UP_SRC` (bit 1, `Z_WU` etc.)
- [ ] 4.2 Sweep `WAKE_UP_THS` from 1 (~31 mg) to 10 (~310 mg) — for each, capture 20 firm taps + 20 light taps + 1 hour mounted noise. Record true-positive and false-positive rates
- [ ] 4.3 Pick the lowest threshold where false positives ≤1/hour AND light-tap detection ≥95%. If no value satisfies both, Path B fails the bar
- [ ] 4.4 Confirm that at the chosen threshold, the WAKE_UP path produces a single INT1 per impact (no rebound double-fire) — if the rebound also clears WAKE_UP_THS, Path B has the same problem as Path A

## 5. Path C — raw-accel + firmware classifier (only if A and B fail)

- [ ] 5.1 Sketch the classifier: peak detection, rebound-amplitude ratio test, inter-peak timing test. Tune against the §2.2 corpus
- [ ] 5.2 Estimate code size, battery cost (extra wake duration × draw current × wakes-per-day), and validation effort. Decide if cost is justified vs. operator's reliability bar
- [ ] 5.3 If pursued: prototype, validate against §2.2 captures, measure per-wake latency added to `tick()`. If latency >100 ms or accuracy <95%, fall back

## 6. Decide and document

- [ ] 6.1 Fill in the decision matrix in `design.md` with measured numbers
- [ ] 6.2 Write a short "findings" section at the bottom of `design.md`: which path won, why, what trade-offs were accepted
- [ ] 6.3 If a viable software path exists: open a follow-up *implementation* openspec change (`implement-single-tap-<chosen-path>`) referencing this research. The implementation change carries the spec deltas (`device-firmware`) and the firmware tasks
- [ ] 6.4 If no software path meets the bar: document explicitly in design.md, escalate to hardware (Paths D or E) as a separate proposal — but only if the operator wants to invest

## 7. Acceptance for this research change

- [ ] 7.1 §1, §2 complete (criterion set, captures collected)
- [ ] 7.2 At minimum Path A explored end-to-end (§3 complete)
- [ ] 7.3 Decision documented (§6.1, §6.2)
- [ ] 7.4 Either a follow-up implementation proposal exists, OR a "no viable path" finding is recorded with reasoning
