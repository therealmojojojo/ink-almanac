## Context

This is the physical change — it produces no code, requires no specs in the usual sense, but benefits from the same discipline. Writing the build as an auditable spec forces the operator to think through the irreversible steps (drilling, gluing) before doing them, and provides a future contributor (or future-self after hardware damage) with a reproducible plan.

## Goals / Non-Goals

**Goals:**
- A clean, repeatable build that can be redone after a hardware failure.
- Clear separation between reversible steps (flashing, testing) and irreversible ones (drilling, gluing).
- Documented physical properties so future changes (different frame, different fridge) can be reasoned about.
- Safety: battery polarity, thermal behavior, cable strain — all explicitly checked.

**Non-Goals:**
- Perfect craftsmanship. The frame should look intentional, not furniture-grade.
- Multiple mount methods. One approach, one fridge, one finished state.
- Field-replaceable parts. If a component fails after gluing, the frame is disassembled or replaced; we don't spec a modular mount.

## Decisions

### Pre-flight the electronics before any permanent operation

The single most expensive mistake in this kind of build is gluing a non-functional board into a frame. The spec mandates a working Summary render before any hole is drilled. Rationale: minutes of verification save hours of rework.

### Plywood backing instead of the stock cardboard

Rationale: cardboard flexes, doesn't hold screws or magnets, and absorbs moisture. Plywood is rigid, easy to drill, takes adhesive well, and can be replaced cheaply. 3mm is enough for structural rigidity without adding weight.

### Six magnets, not four

Rationale: six gives redundancy (losing one is not catastrophic), better load distribution (reducing stress on any single adhesive point), and feels solid on the fridge. Four is workable; six is safer. The 30mm-from-PCB rule keeps the magnetic field away from the battery and the microSD slot.

### E6000, not epoxy

Rationale: E6000 is flexible after curing (absorbs mild vibration without cracking), bonds to painted metal and plastic, and cures in ~24–48h. Epoxy is rigid and can crack over temperature swings. For a fridge-mounted device that may see the fridge opening and closing thousands of times, flex matters.

### IKEA RÖDALM as the default frame

Rationale: inexpensive, consistent dimensions, 25mm+ interior depth (enough for the Inkplate + battery + mounting), glass front (doesn't yellow), widely available in Romania. Alternatives exist; this is the documented default.

### USB-C panel-mount over removable charging

The alternative is to remove the frame, plug in, recharge, remount. Unacceptable — requires breaking the magnet seat every 6 weeks. Panel-mount means charging is a kitchen-counter operation.

### Gyroscope orientation matters for the door filter

The LSM6DSO must be mounted with its axes aligned to the frame's plane so the firmware's vertical-axis rotation detection makes sense. The spec mandates alignment; implementation marks the correct orientation on the IMU before gluing.

### IMU INT1 shares the SW3 wake-button net (GPIO 36)

Inkplate 10 V1.3.1 has no free RTC-capable GPIO exposed on a header — every ADC/wake-capable pin is claimed by the panel data bus, SD card, expander INT, RTC INT, battery sense, or the wake button. The cleanest non-destructive option is to solder the LSM6DSO's INT1 directly onto the SW3 wake-button net (GPIO 36, with on-board R41 pull-up). With INT1 configured open-drain active-low, the sensor pulses the same line low that the button would, and the firmware's `esp_sleep_enable_ext0_wakeup(GPIO_NUM_36, LOW)` (already used by the official Inkplate 10 wake-button example) handles both events identically. Disambiguation happens after wake by reading `WAKE_UP_SRC` over I²C — if no tap bit is set, the pulse came from elsewhere (button, EMI) and the device re-sleeps without refreshing.

Rationale: cutting JP2 (free IO39) or JP4 (free IO34) is reversible but removes existing functionality (RTC INT, expander INT) for a hobby gain. Soldering to the WROVER-E module pin for IO26 is electrically clean but mechanically risky on a board we depend on. The wire-share has zero hardware cost, no jumper modifications, and matches the firmware path the library already documents — the wake button simply becomes a redundant trigger on a net the IMU now shares.

### Documented build log

Rationale: the operator's time, decisions, and deviations ARE the knowledge. A build log captured at the time is vastly more useful than reconstructed memory. `docs/build/build-log.md` is committed so it's durable; photos can be external if too large.

### 30-day mount check as the acceptance criterion

Magnet failures, adhesive creep, cable strain — all problems surface over weeks, not hours. A 30-day check gives confidence that the build will last. Less than 30 days and we're hoping; more than 30 is overkill for a single-operator build.

## Risks / Trade-offs

- **Irreversibility of drilling and gluing.** Every mistake is expensive. Mitigation: the pre-flight requirement, the recommendation for framing-shop mat cutting if in doubt, and explicit "rehearsal" steps in tasks.

- **Magnet strength on non-flat fridges.** Some fridges have textured or curved surfaces that reduce effective magnet contact. Mitigation: the 48-hour cure + 10-minute hang test is an early detection; if the frame slips, operator can add a seventh magnet or switch to command-strip hybrid.

- **Battery positioning.** Battery must not contact heat-generating components (Inkplate's ESP32 area). Mitigation: foam tape spacer, routing documented, thermal check.

- **PIR false-positive from motion behind the frame.** Fridge compressor vibration can register on a cheap PIR. Mitigation: choose a PIR with adequate directional lens; verify in situ; tune the firmware debounce.

- **Cable pinch during insertion.** Mounting the frame can pinch the easyC chain or battery lead. Mitigation: route cables before final close-up, verify freedom of movement.

- **Mat-cutting accuracy.** A wobbly mat looks amateur. Mitigation: use a mat cutter with a straight-edge guide, or go to a framing shop (Bucharest has several near Piața Amzei or Piața Victoriei).

- **Post-build firmware updates.** If OTA is working, no issue. If OTA breaks, USB access requires opening the frame. Mitigation: the pre-flight ensures OTA works before final assembly.

## Migration Plan

Not a migration — a one-time physical build. Executed in sequence:

1. Inventory and verify materials.
2. Flash firmware; verify Summary renders correctly.
3. Disassemble frame; prepare plywood back; cut front mat.
4. Drill PIR hole, USB-C hole, magnet screw holes.
5. Mount electronics; verify connectivity and basic render again inside the frame.
6. Glue magnets; cure 24–48 hours.
7. Mount to fridge; 10-minute hang test.
8. Weekly checks for 4 weeks; log any issues.
9. Archive with a clean build log.

Rollback: if the build fails, the frame is disassembled and rebuilt with replacement parts. The Inkplate and sensors survive if the build is done carefully. Plywood backings are cheap; frames are cheap; time is the main cost.

## Open Questions

1. **Framing shop or home mat-cutting.** A framing shop produces cleaner mats but costs ~50–100 RON. Operator preference; defer.

2. **Glass: keep or remove.** The glass dims the e-paper slightly but protects it from kitchen grease and splashes. Probably keep. Revisit if readability suffers.

3. **Final center of gravity.** The battery is a dominant mass; if it ends up significantly off-center, the frame may want to pivot. Mitigation during assembly: arrange the battery and Inkplate so the CG is near the geometric center. Measure and record.

4. **Whether to paint the plywood.** If visible through gaps, plywood looks hobbyist. Mitigation: paint matte black if visible. Defer to visual inspection during assembly.

5. **Long-term magnet decay.** N42 magnets lose a fraction of a percent of strength per decade; not a practical concern for this timescale. Noted for completeness.
