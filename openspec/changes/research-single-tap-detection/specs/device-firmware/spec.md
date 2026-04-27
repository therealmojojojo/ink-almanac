# device-firmware — delta

## ADDED Requirements

### Requirement: Single-tap detection research is a precondition to single-tap-as-distinct-gesture

Before any firmware change SHALL treat single-tap as a meaningful gesture distinct from double-tap, the investigation in `research-single-tap-detection` SHALL produce:

1. A measured characterisation of the wire-tied frame mount's rebound profile (delay, amplitude ratio).
2. A pass/fail evaluation of at least Path A (DUR window tightening) against the operator's reliability bar.
3. An explicit decision document recording which path (A, B, C, D, or E) was selected, OR a "no viable software path" finding with reasoning.

The current "every tap latches DOUBLE_TAP, HA collapses both kinds to the same intent" behavior MAY remain in place during the research and after, until an implementation change supersedes it.

#### Scenario: Implementation change proposed without research findings

- **WHEN** a future implementation proposal claims to make single-tap distinct from double-tap
- **AND** the proposal does not reference a completed `research-single-tap-detection` change with measured findings
- **THEN** the implementation proposal SHALL be rejected during review until the research is complete and its findings inform the chosen path

#### Scenario: Research concludes with a viable software path

- **WHEN** the research change archives with a chosen path
- **THEN** a follow-up implementation change `implement-single-tap-<chosen-path>` SHALL carry the actual firmware deltas (IMU init register changes, `drainPendingTap` decode changes, test scenarios), AND this requirement is satisfied

#### Scenario: Research concludes no software path meets the reliability bar

- **WHEN** the research change archives with a "no viable software path" finding
- **THEN** the device-firmware capability SHALL continue to treat all taps as DOUBLE (current behavior), AND any further pursuit of single-tap distinction SHALL be a hardware-side proposal (rigid mount or external piezo) outside this capability's scope
