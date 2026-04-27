## 1. Sourcing

- [ ] 1.1 Purchase IKEA RÖDALM (or verified equivalent ≥25mm interior depth)
- [ ] 1.2 Cut or purchase 3mm plywood/hardboard backing sized to the frame
- [ ] 1.3 Purchase 6× N42 neodymium disc magnets, 15–20mm × 3mm
- [ ] 1.4 Purchase E6000 adhesive, double-sided foam tape, small screws
- [ ] 1.5 Acquire 9mm and 11–12mm drill bits
- [ ] 1.6 Confirm all Inkplate-related components from Soldered order are present and unopened

## 2. Pre-flight

- [ ] 2.1 Flash firmware via USB with `secrets.h` configured for the local environment
- [ ] 2.2 Power on; verify boot, WiFi connection, MQTT connection
- [ ] 2.3 Fetch and render Summary mode; confirm the face displays correctly
- [ ] 2.4 Cycle through mode fetches (Weather, Gallery, Night) to confirm all work
- [ ] 2.5 Confirm R41 pulls GPIO 36 high (~3.3 V) at idle with a multimeter — establishes the INT1 polarity decision below
- [ ] 2.6 Solder INT1 from the LSM6DSO breakout onto the SW3 wake-button net (either SW3 pad, the GPIO-36 side of R41, or the K37 header pin — whichever is mechanically easiest)
- [ ] 2.7 Run tap detection tests on the bench; confirm a double-tap on the IMU wakes the ESP32 from deep sleep exactly as the wake button would (tap → `ext0` LOW → wake → `WAKE_UP_SRC.DOUBLE_TAP` set)
- [ ] 2.8 Bench-test the false-positive guard: tap the surface lightly and slam a nearby drawer; confirm only deliberate Z-axis double-taps survive the post-wake `WAKE_UP_SRC` check
- [ ] 2.9 Run PIR wake test
- [ ] 2.10 Verify OTA update round-trip works
- [ ] 2.11 Commit the pre-flight result to `docs/build/build-log.md`

## 3. Frame preparation

- [ ] 3.1 Disassemble the frame; remove cardboard backing and any spacer
- [ ] 3.2 Cut 3mm plywood to the frame's interior dimensions
- [ ] 3.3 Cut front mat to expose 9.7" active area with even border (or take to framing shop)
- [ ] 3.4 Dry-fit: plywood, mat, Inkplate all assemble cleanly with the glass on

## 4. Drilling

- [ ] 4.1 Mark PIR lens position on the plywood (bottom-center or bottom-right)
- [ ] 4.2 Mark USB-C panel-mount position on the bottom edge
- [ ] 4.3 Mark 6 magnet positions: 4 corners + 2 mid-edges, keeping ≥30mm from where electronics will sit
- [ ] 4.4 Drill 9mm PIR lens hole
- [ ] 4.5 Drill 11–12mm USB-C panel-mount hole
- [ ] 4.6 Drill magnet screw holes (if using screw-mounted magnets) or skip if adhesive-only

## 5. Electronics mounting

- [ ] 5.1 Attach battery to plywood with double-sided foam tape (clear of the Inkplate's heat zone)
- [ ] 5.2 Mount Inkplate centered to plywood with foam tape or non-marring fasteners
- [ ] 5.3 Glue LSM6DSO to the inside back with axes aligned to the frame plane (y-axis parallel to gravity when hung)
- [ ] 5.4 Insert PIR through its front-plastic hole; secure with a small bead of hot glue or double-sided tape
- [ ] 5.5 Connect easyC chain: Inkplate → LSM6DSO → PIR
- [ ] 5.6 Route USB-C panel-mount to the Inkplate's USB port
- [ ] 5.7 Verify battery polarity before plugging in
- [ ] 5.8 Plug in battery; power-on test; confirm render still works with the new wiring

## 6. Magnets

- [ ] 6.1 Clean magnet positions with isopropyl alcohol
- [ ] 6.2 Apply E6000 generously to each magnet
- [ ] 6.3 Place magnets at the marked positions
- [ ] 6.4 Allow to cure undisturbed for 24 hours minimum, 48 hours recommended

## 7. Final assembly

- [ ] 7.1 Re-check all cable connections; confirm no wires are pinched
- [ ] 7.2 Close the frame with the glass and mat
- [ ] 7.3 Power-on; verify all modes display correctly through the glass
- [ ] 7.4 Test charging via the USB-C panel-mount with the frame fully assembled

## 8. Mount and verify

- [ ] 8.1 Mount to fridge at the intended position
- [ ] 8.2 Leave for 10 minutes; confirm no slipping
- [ ] 8.3 Perform tap-detection test with frame on the fridge; verify the door filter suppresses fridge-open taps
- [ ] 8.4 Let the device run for 24 hours; confirm no thermal issues, all modes transitioning correctly

## 9. 30-day mount check

- [ ] 9.1 Week 1 check: photograph, log any issues
- [ ] 9.2 Week 2 check
- [ ] 9.3 Week 3 check
- [ ] 9.4 Week 4 check: if clean, the spec's mount-check acceptance criterion is met

## 10. Build log

- [ ] 10.1 Compile photos into `docs/build/` (gitignored if large)
- [ ] 10.2 Write `docs/build/build-log.md` with:
  - Build date
  - Materials deviations
  - Measured weight
  - Approximate center of gravity
  - Hardware issues encountered
  - Lessons learned
- [ ] 10.3 Commit the build log
