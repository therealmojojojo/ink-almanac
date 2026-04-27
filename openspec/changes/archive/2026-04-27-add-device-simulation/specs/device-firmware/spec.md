## ADDED Requirements

### Requirement: HAL-based structure

The firmware SHALL route all hardware interactions through interface-based abstractions (the Hardware Abstraction Layer, defined by `device-simulation`). The main loop, wake-handling, override management, door-filter logic, and power-budget accounting SHALL reference HAL interfaces rather than concrete hardware libraries.

Concrete on-device implementations live in `firmware/src/hal/real/`. Mock implementations for simulation live in `firmware/test/hal/mock/`. The same firmware sources compile against either.

#### Scenario: Refactor preserves behavior

- **WHEN** the HAL-based firmware is flashed to the Inkplate and runs through each scenario from `device-firmware` and `device-wake-protocol`
- **THEN** behavior is identical to a hypothetical direct-call implementation; the refactor is purely structural

#### Scenario: Hardware library dependency attempt outside HAL

- **WHEN** a code change adds `#include <Inkplate.h>` in a non-HAL file
- **THEN** a pre-commit or CI check flags the import as a HAL-boundary violation
