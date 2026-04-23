## Why

The dashboard only becomes a fridge-mounted picture frame after someone cuts mats, drills holes, routes cables, and glues magnets. This change captures that physical work as an auditable, repeatable process — not because it's deeply clever, but because doing it right matters and the details (hole sizes, magnet count, adhesive cure time) are easy to forget.

It also gives the project's acceptance criteria their physical anchors: "mounts cleanly on fridge without slipping over 30 days", "does not expose to >60°C", etc. Without this change, those criteria have no home.

## What Changes

- Source and inventory the physical materials: picture frame, plywood backing, magnets, adhesives, drill bits, panel-mount USB-C extension.
- Assemble the Inkplate + battery + LSM6DSO + PIR + USB-C extension inside the frame per the documented steps.
- Drill the frame backing for the PIR lens (9mm) and USB-C panel-mount (11-12mm).
- Mount six N42 neodymium magnets to the frame back with E6000 adhesive, distributed away from the electronics.
- Verify mount on the fridge: no slipping, no excessive overhang, reach-in comfort for tap gestures.
- Validate thermal and physical safety: battery polarity correct, no wire pinch points, no components near >60°C zones.
- Document the build with photos of each step, stored in `docs/build/`.
- Capture measured physical properties: weight, center of gravity, magnet holding force on the actual fridge.

## Capabilities

### New Capabilities

- `physical-build`: The materials list, assembly sequence, mounting method, safety verification, and build documentation for the fridge-mounted dashboard.

### Modified Capabilities

None.

## Impact

- **New documentation**: `docs/build/` directory with per-step photos and notes.
- **No code changes**.
- **Prerequisites**: hardware components purchased and in hand; `add-device-firmware` at least flashable (so the Inkplate is responsive before gluing); mat-cutting tools or a framing shop engaged.
- **Blocks**: the dashboard cannot hang on the fridge until this change completes. Acceptance criteria from other capabilities that reference physical behavior (power budget under real mounting, tap detection under real mounting conditions) can only be verified after this change applies.
- **Risk**: irreversible operations (drilled holes, cured adhesive). Once this change applies, the hardware is committed. Mitigation: spec includes a rehearsal step before permanent operations.
