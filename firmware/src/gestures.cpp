#include "gestures.h"

namespace fw::gestures {

TapKind readTapKind(hal::IIMU& imu) {
  bool is_double = false;
  if (!imu.drainPendingTap(&is_double)) return TapKind::None;
  return is_double ? TapKind::Double : TapKind::Single;
}

}  // namespace fw::gestures
