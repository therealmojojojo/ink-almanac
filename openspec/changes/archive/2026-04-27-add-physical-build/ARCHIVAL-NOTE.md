# Archival note — 2026-04-27

This change documented the *intent* to assemble and verify the physical
build (frame, plywood, magnets, drilled USB-C and PIR holes, mounted
electronics, fridge mount). The hardware referenced by the rest of this
repo is **operational** (the device is on the fridge, IMU taps register,
WiFi connects, panel refreshes), so the build itself happened — but
the documentation artefacts the proposal called for (`docs/build/`,
photos, build-log.md, thermal/safety verification record) were never
captured during the work and don't exist in the repo today.

Archived because:
- The build is done. Re-running these tasks against the live device
  would be either destructive (drilling, gluing) or pointless (the
  device works).
- The proposal still has reference value: if a second unit is ever
  built, this is the closest we have to a procedure document.

If documentation is needed post-hoc:
- Reproduce from memory and add to `firmware/docs/hardware-build.md`
  (preferred home — that directory already holds power and wake-protocol
  docs).
- Photograph the live device's mount, drill placements, and PIR cutout.
- Capture battery cell type / cell-protection-circuit details for next
  unit's BOM.

For new-unit builds, treat this proposal as the starting checklist;
reopen as a fresh change before any drilling happens.
