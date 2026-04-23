#pragma once

#include "hal/HAL.h"

namespace fw::gestures {

enum class TapKind { None, Single, Double };

// Read the tap kind from the IMU's event register.
// Returns TapKind::None if no event is pending.
TapKind readTapKind(hal::IIMU& imu);

}  // namespace fw::gestures
