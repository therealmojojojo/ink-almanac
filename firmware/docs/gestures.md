# Gestures

## Tap detection

The LSM6DSO provides hardware tap / double-tap detection. The firmware
configures registers `TAP_CFG0`, `TAP_THS_6D`, `TAP_DUR` and routes
`INT1` to **GPIO 36** as an `ext0` deep-sleep wake source (shared with
the SW3 wake button — see "Wiring" below).

On wake with `Reason::IMU`, the firmware:

1. **Snapshots `TAP_SRC` immediately in `RealIMU::init()`, before any
   other register write.** Re-writing `CTRL1_XL` (or related config)
   restarts the accelerometer pipeline and clears the chip's tap-event
   latch, so reading `TAP_SRC` after re-init returns `0x00`. The init
   reads first, caches the value in a member, and `drainPendingTap()`
   later returns the snapshot. The same read also un-latches INT1, so
   R41 restores the idle HIGH on IO36 for the next event.
2. In `tick()`, if the cached `TAP_SRC` has neither `SINGLE_TAP` (bit 5)
   nor `DOUBLE_TAP` (bit 4) set, the LOW pulse on GPIO 36 came from
   something other than the IMU — SW3 in operator mode, EMI, or a
   sub-threshold accelerometer event. The firmware skips the entire
   tick (no WiFi, no fetch, no e-paper refresh), re-arms the same wake
   sources, and goes straight back to deep sleep. This guard makes
   spurious lows free.
3. Otherwise, classify the event from the `DOUBLE_TAP` bit and publish
   `{"kind":"single"|"double"}` on `inkplate/state/gesture`.

HA reacts to the gesture: single-tap → Weather peek; double-tap → toggle
Summary/Gallery (no-op during Night-scheduled hours).

### Single vs double in practice

The chip distinguishes single from double using the DUR window in
`INT_DUR2`. With `SINGLE_DOUBLE_TAP=1` (current), a tap is classified as
`DOUBLE_TAP` if a second impulse arrives within DUR (~308 ms at 416 Hz
ODR), otherwise `SINGLE_TAP`. A natural finger tap on a small breakout
often produces a low-amplitude rebound 100–300 ms after the primary
impulse, which falls inside DUR and so gets classified as double. To
absorb the rebound the firmware sets `INT_DUR2.QUIET=3` (max ~29 ms),
but rebounds outside QUIET-but-inside-DUR still register as second
taps. The pragmatic outcome on this hardware: most natural single taps
read as `DOUBLE_TAP`. If the toggle semantics matter and single-tap
detection doesn't, set `WAKE_UP_THS.SINGLE_DOUBLE_TAP=0` so every tap
reads as single.

## Wiring

INT1 from the LSM6DSO breakout is soldered onto the SW3 wake-button net
(GPIO 36, with the on-board R41 pull-up to 3V3). Both the button (when
accessible) and the sensor's INT1 pulse the same line low — from the
ESP32's `esp_sleep_enable_ext0_wakeup(GPIO_NUM_36, LOW)` perspective the
two events are indistinguishable, and the post-wake `WAKE_UP_SRC` read
above is the only way to tell them apart. In the sealed-frame build SW3
is unreachable, so practically every IO36 LOW originates from INT1.

For this to work the LSM6DSO INT1 must be configured as **open-drain,
active-low**:

- `CTRL3_C[PP_OD]=1` — open-drain output (sinks LOW or floats high-Z;
  never drives HIGH, so it can't fight R41 or the button).
- `CTRL3_C[H_LACTIVE]=1` — active-low polarity.
- Pulsed (not latched) interrupt mode — INT1 returns to high-Z after the
  tap window so R41 restores the idle HIGH; otherwise the device would
  re-wake the moment it tries to sleep.

To minimize false wakes from fridge-door slams the firmware enables tap
detection on the **Z axis only** (`TAP_CFG0[TAP_Z_EN]=1`, X and Y
disabled) — Z is perpendicular to the fridge surface where deliberate
finger taps land; door slams mostly excite X/Y.

## Tuning

Threshold and double-tap windows live in `firmware/include/config.h`:

| Constant | Bench value | Mounted target |
|---|---|---|
| `kTapThreshold` | 2 (~125 mg) | 12–20 (~0.75–1.25 g) |
| `kDoubleTapWindowMs` | 350 | unchanged |

The threshold is intentionally low for the unmounted breakout because a
loose PCB absorbs much of the impact. Once the breakout is coupled to
the inner frame surface — operator's build glues a toothpick to the back
of the breakout and tapes the toothpick to the wood, which transmits
taps cleanly via the rigid lever — taps couple far better and ambient
kitchen vibration can latch tap bits at threshold = 2 (slipping past the
spurious-wake guard). Raise `kTapThreshold` to 12–20 after the build is
mounted and observe real-world false-positive rates over a few days.

Bench validation (April 2026): threshold = 2, QUIET = 3, Z-only,
`SINGLE_DOUBLE_TAP=1`, on USB and on battery (~4.23 V) — taps register
reliably as `DOUBLE_TAP`, gestures publish to `inkplate/state/gesture`,
HA's automation evaluates correctly (no-op during Night, toggle outside
Night), spurious-wake guard suppresses ~80% of ext0 fires that don't
correspond to real taps.

## Latched-tap polling (fallback)

If INT1 is not soldered (bench-test config, or before final assembly),
the device can't `ext0`-wake on a tap. LSM6DSO's `LATCHED_INT` bit keeps
the event visible across deep sleep, so every Timer wake drains
`TAP_SRC`; if a tap is pending, the wake reason is upgraded to IMU.
Worst-case latency is one timer period (~60 s). This path is also a
safety net if the INT1 wire breaks in the field.
