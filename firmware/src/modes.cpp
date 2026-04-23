#include "modes.h"

#include "config.h"

namespace fw::modes {

int timerSeconds(Mode m) {
  using namespace fw::config;
  switch (m) {
    case Mode::Summary:    return kSummaryTimerSec;
    case Mode::Weather:    return kWeatherTimerSec;
    case Mode::Gallery:    return kGalleryTimerSec;
    case Mode::Night:      return kNightTimerSec;
    case Mode::NowPlaying: return 0;  // no timer wake in now-playing
    case Mode::Unknown:    return kSummaryTimerSec;
  }
  return kSummaryTimerSec;
}

}  // namespace fw::modes
