## MODIFIED Requirements

### Requirement: Shared conventions across all faces

All faces SHALL adhere to shared visual conventions:

- Outer padding of 36u top/bottom and 48u left/right
- Battery percentage indicator in the top-right corner in micro-sized IBM Plex Mono (exception to the 25u size floor). The indicator's value SHALL be sourced from the `device` input — specifically `device.battery.percentage` — on every face. Faces SHALL NOT source the battery value from any other input (it is device state, not climate, Sonos, or pairing state).
- Mode identity is implicit through content and layout; no explicit "SUMMARY" label is drawn anywhere
- Rules are 1u solid or 1u dashed `--faint` (`#a8a8a8`); section dividers are 2u solid `--ink` (`#000`)
- All zones SHALL provide a graceful-degradation treatment when required data is null or unavailable

#### Scenario: Battery indicator placement

- **WHEN** any face is rendered with `device.battery.percentage = 82`
- **THEN** the top-right corner displays a small battery glyph followed by `82%` in IBM Plex Mono

#### Scenario: Battery indicator on every face

- **WHEN** Weather, Gallery, Night, or Now-Playing is rendered with `device.battery.percentage = 82`
- **THEN** each face shows `82%` in the top-right, identical to Summary's treatment — the indicator is not Summary-only

#### Scenario: Device input missing

- **WHEN** `device.json` is absent at render time
- **THEN** every face renders with the battery indicator showing an em-dash label in place of the percentage

#### Scenario: Missing-data fallback

- **WHEN** a zone's required data is null at render time
- **THEN** the zone displays a minimal placeholder (empty rule, short em-dash, or blank) without breaking the layout; the renderer does NOT refuse to render
