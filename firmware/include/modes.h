#pragma once

#include <string>

namespace fw::modes {

enum class Mode { Unknown, Summary, Weather, Gallery, Night, NowPlaying };

constexpr const char* toString(Mode m) {
  switch (m) {
    case Mode::Summary:    return "summary";
    case Mode::Weather:    return "weather";
    case Mode::Gallery:    return "gallery";
    case Mode::Night:      return "night";
    case Mode::NowPlaying: return "now-playing";
    case Mode::Unknown:    return "unknown";
  }
  return "unknown";
}

inline Mode parse(const std::string& s) {
  if (s == "summary")     return Mode::Summary;
  if (s == "weather")     return Mode::Weather;
  if (s == "gallery")     return Mode::Gallery;
  if (s == "night")       return Mode::Night;
  if (s == "now-playing") return Mode::NowPlaying;
  return Mode::Unknown;
}

// Timer cadence per mode, in seconds. Zero means "don't timer-wake in this mode".
int timerSeconds(Mode m);

}  // namespace fw::modes
