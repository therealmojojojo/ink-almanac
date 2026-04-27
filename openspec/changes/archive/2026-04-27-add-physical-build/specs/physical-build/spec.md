## ADDED Requirements

### Requirement: Materials inventory

Before assembly begins, the operator SHALL have the following materials on hand and verified:

- Inkplate 10 board (9.7", 1200×825, 3-bit)
- Soldered 5000mAh Li-Po battery with pre-wired JST-PH connector
- LSM6DSO 6-DoF IMU breakout (easyC)
- PIR motion sensor breakout (easyC)
- Qwiic/easyC cables for sensor chaining
- Round USB-C panel-mount extension for in-place charging
- Picture frame, preferably IKEA RÖDALM or equivalent, with interior depth ≥ 25mm
- 3mm plywood or hardboard backing panel, sized to replace the frame's cardboard back
- 6× N42 nickel-plated neodymium disc magnets, 15–20mm × 3mm
- E6000 adhesive (or equivalent), double-sided foam tape, small screws
- 9mm and 11–12mm drill bits

#### Scenario: Materials check complete

- **WHEN** the operator confirms every item is on hand
- **THEN** the build may proceed; absent items halt the build until sourced

### Requirement: Pre-flight validation

The Inkplate SHALL be flashed with a working firmware build and verified to render at least one mode (e.g., Summary) successfully before any permanent physical operation. This ensures electronics work BEFORE they are glued inside a frame.

#### Scenario: Pre-flight pass

- **WHEN** the Inkplate is connected to WiFi and fetches `/display/summary.png`, displaying it correctly
- **THEN** the build may proceed to the drilling and gluing phases

#### Scenario: Pre-flight fail

- **WHEN** the Inkplate does not render or drops its connection
- **THEN** the build halts and the electronics issue is resolved before any physical-build step continues

### Requirement: Backing and mat preparation

The frame's cardboard back SHALL be replaced with a 3mm plywood (or hardboard) panel cut to the frame's interior dimensions. A front mat SHALL be cut to expose the Inkplate's 9.7" active area (approximately 197mm × 135mm) with an even border against the frame's interior opening.

#### Scenario: Mat fits flush

- **WHEN** the operator assembles the frame with the cut mat
- **THEN** the Inkplate's active area is fully visible through the mat opening, the mat is square with the frame, and no Inkplate chrome or body is visible around the edges

### Requirement: Holes

Two holes SHALL be drilled through the plywood backing:

- **PIR lens hole**: 9mm diameter, positioned at bottom-center or bottom-right of the backing, where the PIR's lens can look out at the operator's approach
- **USB-C panel-mount hole**: 11–12mm diameter, positioned at the bottom edge of the backing, routed to a location that does not obstruct magnets or battery

Six additional screw holes SHALL be drilled at the magnet-mount positions (4 corners + 2 mid-edges), deep enough to recess the magnets flush with the backing surface.

#### Scenario: Holes drilled and positioned

- **WHEN** the operator completes the drilling
- **THEN** the PIR lens protrudes through the 9mm hole with no binding, the USB-C extension fits flush in the 11–12mm hole, and the 6 magnet screw holes are in non-interfering positions

### Requirement: Electronics mounting

The Inkplate SHALL be centered behind the mat, mounted to the plywood backing with non-marring fasteners or foam tape. The battery SHALL sit flat against the plywood with double-sided foam tape, clear of the Inkplate's heat-generating components.

The LSM6DSO SHALL be glued to the inside back of the frame with its orientation aligned to the frame plane (the `y` axis of the IMU parallel to the gravity vector when the frame is hung in its intended orientation). The PIR lens SHALL protrude through its 9mm hole in the front plastic.

The easyC daisy-chain SHALL connect: Inkplate → LSM6DSO → PIR. The USB-C panel-mount extension SHALL route to the Inkplate's USB port.

#### Scenario: Electronics mounted correctly

- **WHEN** the operator finishes mounting
- **THEN** battery polarity is verified correct (matches Inkplate's JST-PH connector polarity), no wires are pinched or strained, all easyC connections are seated, and a quick power-on confirms the device still boots

### Requirement: Magnet mounting

Six N42 neodymium magnets SHALL be glued to the backing at the positions defined by the drill holes, using E6000 adhesive. Magnets SHALL be distributed away from the electronics (particularly the battery and the Inkplate's microSD slot and RTC crystal) to avoid interference with sensitive components. The adhesive SHALL cure for at least 24 hours before the frame is weight-tested, and 48 hours is recommended for full strength.

#### Scenario: Magnet placement

- **WHEN** the magnets are placed
- **THEN** each is at least 30mm from the nearest PCB edge, no magnet is directly behind the battery, and the spacing across the 6 magnets distributes the holding force evenly

#### Scenario: Post-cure weight test

- **WHEN** the operator applies the frame to a steel fridge 48 hours after gluing and lets it hang for 10 minutes
- **THEN** the frame does not slip, no magnet detaches, no adhesive creaks

### Requirement: Thermal and physical safety

The assembled frame SHALL NOT be exposed to sustained temperatures above 60°C (LiPo battery thermal limit). The operator SHALL verify that no part of the Inkplate or battery contacts the inside of the frame in a way that inhibits heat dissipation. Cable routing SHALL not place wires under tension during normal mounting and charging operations.

#### Scenario: Thermal check

- **WHEN** the assembled frame has been operating for 24 hours on the fridge
- **THEN** the frame's surface temperature is close to ambient, not warm to the touch, and the battery charge is within expected bounds

### Requirement: Charging access

The USB-C panel-mount extension SHALL allow charging in place without removing the frame from the fridge. The charging cable SHALL be unobtrusive when inserted and not strain the panel-mount.

#### Scenario: Charging in place

- **WHEN** the operator plugs a USB-C cable into the panel-mount while the frame hangs on the fridge
- **THEN** the cable connects securely, charging begins, the cable's weight does not pull on the frame, and disconnecting is clean

### Requirement: Build documentation

The operator SHALL capture the build in photographs, at minimum:

- Materials laid out
- Backing cut
- Each drilled hole
- Electronics mounted (before and after the magnets)
- Magnet positions
- Mounted frame on the fridge (front and side views)

Photos SHALL be saved to `docs/build/` (gitignored if too large; operator keeps local). A short notes file `docs/build/build-log.md` SHALL be committed recording measurements, deviations from the plan, and any hardware lessons learned.

#### Scenario: Build log complete

- **WHEN** the build is finished
- **THEN** `docs/build/build-log.md` exists with date, materials-deviation notes, measured weight, measured center-of-gravity, and any hardware issues encountered

### Requirement: 30-day mount check

After the frame is mounted on the fridge, the operator SHALL check its position weekly for at least 4 consecutive weeks. Any slippage, detached magnet, or visible adhesive degradation SHALL be recorded in the build log with photos.

The acceptance criterion from this change is: no slipping across 30 days of normal fridge use.

#### Scenario: Month-one check clean

- **WHEN** 30 days have passed since mounting
- **THEN** the frame has not slipped, no magnet has detached, no adhesive has failed, and the build log records the clean check
