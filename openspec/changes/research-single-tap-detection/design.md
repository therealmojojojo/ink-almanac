# Design exploration — single-tap detection on the wire-tied frame mount

## Current state

Source of truth: `firmware/src/hal/real/RealIMU.h` + `firmware/include/config.h`.

```c
// LSM6DSO config at boot:
TAP_CFG0  = 0x0F   // tap on all 3 axes + LATCHED_INT
TAP_CFG1  = 0x21   // priority Z>Y>X (bits 7:5 = 001), threshold = kTapThreshold (1)
TAP_CFG2  = 0x81   // Y-axis threshold = 1, interrupts enabled
TAP_THS_6D = 0x01  // Z-axis threshold = 1
INT_DUR2  = ?      // DUR[3:0] (double-tap window), QUIET[1:0] (post-tap quiet),
                   //  SHOCK[1:0] (max shock duration)
MD1_CFG   = ...    // route DOUBLE_TAP_INT and SINGLE_TAP_INT to INT1
CTRL1_XL  = 0x60   // accel ODR 416 Hz, ±2 g, LPF1 disabled
```

`drainPendingTap`:
```c
uint8_t src = readReg(TAP_SRC);   // bit 6 = TAP_IA, bit 5 = SINGLE, bit 4 = DOUBLE
if (src & 0x10) is_double = true; // DOUBLE_TAP detected
if (src & 0x40) /* tap event */;  // TAP_IA — any latched event
```

Empirical evidence (2026-04-27 serial capture, ~10 firm taps on the mounted device):
- `TAP_SRC` always one of `0x59`, `0x5A` (bits 6, 4, 3, [1 or 0] set)
- `TAP_SRC` bit 5 (`SINGLE_TAP`) never set
- Soft taps below visible threshold produce no INT1 wake at all

## Mount mechanics — observed

Wire-tied frame mount: the IMU board is held against the back of the panel by twisted-wire ties. On impact the panel/frame system has measurable spring-mass behaviour:
- **Initial shock**: ~5-15 ms duration, peak amplitude clears `kTapThreshold`
- **Rebound shock**: arrives ~80-180 ms after initial, ~30-60% of initial amplitude (estimated, not yet measured)
- **Decay**: 2-3 oscillations of decreasing amplitude, fully damped within ~400 ms

The IMU's tap classifier sees the initial as tap-1 and the rebound as tap-2 within `kDoubleTapWindowMs` (350 ms). Result: every cleanly-detected impact latches `DOUBLE_TAP`.

## Investigation paths

### Path A — Tighten the double-tap DUR window

**Idea**: shrink `INT_DUR2.DUR` so the rebound shock arrives *outside* the double-tap window. The classifier would then see the rebound as a separate event from a different gesture entirely (which the firmware can ignore via `LATCHED_INT` re-arm timing, or which times out before any classification).

**Mechanism**: `INT_DUR2.DUR[3:0]` is the maximum delay between two taps for the classifier to call it `DOUBLE`. Units: 32 × 1/ODR. At ODR=416 Hz, 1 unit = ~77 ms; with DUR=2 (~154 ms) the window would close before the rebound at 180 ms — but might still admit a rebound at 120 ms. With DUR=1 (~77 ms), the window closes before any rebound and most deliberate double-taps.

**Pros**:
- Pure register reconfiguration — single-line firmware change
- No new code paths; existing `drainPendingTap` works unchanged once `SINGLE_TAP` starts latching
- Keeps the chip's hardware classifier doing the heavy lifting

**Cons**:
- Eliminates deliberate double-tap as a distinct gesture (human inter-tap delay is typically 200-400 ms, well above any DUR value that excludes the rebound)
- Sensitive to tap force: a softer initial tap means a faster, smaller rebound that still falls in the window; harder taps mean later, larger rebounds. Not a universal cutoff
- Per-mount: if the operator ever moves the device or changes the mount, the rebound timing shifts and the threshold needs re-tuning

**Acceptance criterion**: ≥95% of intentional firm taps land as `SINGLE_TAP`, AND deliberate double-taps (taps within 250 ms intentionally) are unreliably classified — operator must accept "double-tap is dead."

**Investigation tasks**: §3.1, §3.2, §3.3 below.

### Path B — Switch primary detection to WAKE_UP

**Idea**: the LSM6DSO's `WAKE_UP_*` registers detect any acceleration above threshold for `WAKE_UP_DUR` samples. Less stringent than tap (no slope-up-then-down profile), so it captures softer taps the tap classifier misses. WAKE_UP fires the same INT1 line; firmware reads `WAKE_UP_SRC` instead of `TAP_SRC`.

**Pros**:
- More sensitive — captures softer single taps below the tap classifier's floor
- Single hardware event per impact; no rebound classification artefact
- Visual ack becomes 1:1 (one tap, one dot), matches user expectation

**Cons**:
- No hardware-side single/double distinction at all — all events are "movement"
- Must coexist with TAP detection or replace it; coexistence is more code
- Higher false-positive rate: HVAC vibration, fridge compressor cycle, kitchen footsteps near the mount may register
- Need empirical noise-floor measurement in the operator's environment
- `WAKE_UP_THS` is a 6-bit value (0-63 in units of FS/64 = ~31 mg at ±2g). Range: ~31 mg to ~2 g. Lower bound is below the tap classifier's threshold floor, so soft taps that miss tap will hit wake-up

**Acceptance criterion**: ≥95% of intentional taps register, ≤1 false-positive wake per hour during a 24-hour dry run with the panel mounted in operator's kitchen.

**Investigation tasks**: §3.4, §3.5.

### Path C — Raw accelerometer + firmware-side classification

**Idea**: configure the IMU's FIFO to capture accel samples at high rate (e.g., 833 Hz). On INT1 wake, drain the FIFO, run a firmware classifier that looks for the shock-then-rebound pattern. The classifier emits `Single` if only one peak above threshold in a 200 ms window, `Double` if two distinct peaks separated by >150 ms.

**Pros**:
- Most flexible — firmware logic can be tuned per-mount, per-environment
- Distinguishes peak-amplitude-only (firm tap) from peak-and-rebound (frame ring) by measuring relative amplitudes (rebound is consistently weaker)
- Could distinguish deliberate double-tap (two ~equal peaks) from frame ring (one large + one weaker) by amplitude ratio

**Cons**:
- Most code: FIFO config, FIFO drain on every wake, classifier with several tunable parameters
- Battery cost: extra ~50-100 ms of accel reads per wake at 833 Hz (~0.05 mAh per wake)
- Validation surface: needs a test corpus of recorded tap profiles to tune against. Hard to assemble without bench time
- Latency: classifier must complete before `showTapAck` paints the badge, or the visual ack is delayed

**Acceptance criterion**: same as A or B, plus deliberate double-tap reliably distinguished (≥80% accuracy when operator double-taps within 200-300 ms).

**Investigation tasks**: §3.6, §3.7.

### Path D — Mount changes (rigid coupling)

**Idea**: replace wire-ties with adhesive or screw-mount that rigidly couples the IMU to the frame. Eliminates the ringing entirely.

**Pros**:
- Hardware-cured: classifier works as designed, no software workarounds
- Single-tap and double-tap both reliable at the IMU's published spec

**Cons**:
- Hardware rework, possibly destructive to the current mount
- Out of scope for a software-research change — escalates only if all software paths fail their reliability bars

**Acceptance criterion**: not evaluated by this research; flagged as fallback.

### Path E — External tap sensor (piezo / capacitive)

**Idea**: a piezo disc on the bezel front, glued to the top-right corner. Detects finger taps regardless of frame mechanics. Wired to a spare GPIO as a separate ext0 wake source.

**Pros**:
- Sensor designed for the use case, no software gymnastics
- Could potentially register taps the IMU never sees (very light touches)

**Cons**:
- Hardware addition: piezo + analog conditioning + GPIO routing
- Out of scope for this research

**Acceptance criterion**: not evaluated.

## Decision matrix (to be filled in during investigation)

| Path | Soft taps register | Deliberate single distinguishable | Deliberate double distinguishable | Code cost | Battery cost | False-positive rate (24h dry run) |
| --- | --- | --- | --- | --- | --- | --- |
| A — DUR tighten | no (still below threshold) | yes (if DUR cuts before rebound) | NO (sacrificed) | ~5 lines | ~0 | TBD |
| B — WAKE_UP | YES | yes (one event = one tap) | NO (sacrificed) | ~30 lines | ~0 | TBD |
| C — raw accel + FW classify | depends on accel sensitivity | yes | yes (potentially) | ~150 lines | +0.05 mAh/wake | TBD |
| D — rigid mount | n/a | yes | yes | n/a (hardware) | n/a | n/a |
| E — piezo | yes | yes | yes | ~50 lines + HW | TBD | TBD |

## Recommended sequencing

1. **Capture data first** (§3.1, §3.4, §3.5) — without measurements, all four paths are hand-waving. Get an oscilloscope trace or raw-accel sample of 20+ tap impacts and 1 hour of background noise.
2. **Try Path A** as the cheapest experiment: change `INT_DUR2.DUR`, observe whether `SINGLE_TAP` starts latching. If it does AND the operator confirms they don't need deliberate double-tap, we're done with software work. If it doesn't (rebound timing is too consistent or the cut value is too tight to be human-friendly), continue.
3. **Try Path B** if A fails: requires more code but no firmware-side classifier. A 24-hour dry run is the only honest evaluation.
4. **Path C only if A and B both fail.** It's a ~150-line refactor with real validation cost; not worth it if A or B works.
5. **Paths D and E are escalations** if software-only paths don't meet the reliability bar.

## Operator preferences captured 2026-04-27

- The current "tap-as-double + HA collapses to same intent" is *acceptable behavior* and shipping. Don't disrupt it during research.
- Cosmetic fixes that bypass the IMU's classifier output (e.g., always render 1 dot regardless of `DOUBLE_TAP` bit) were considered and **declined** — the system's report is accurate ("I have to double-tap to make it work"), and masking that signal hides the real diagnostic.
- The investigation explicitly targets **single-tap as a distinct meaningful operation**, not just visual cosmetics.
