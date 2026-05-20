#pragma once

#include <cstdint>
#include <ostream>
#include <string>

#include "hal/types.h"
#include "modes.h"

namespace fw::wake {

// Wake reasons. `pir` removed — motion now lives in HA (see
// openspec/changes/move-pir-to-ha-motion/); HA-driven wakes arrive as
// `HACommand`.
enum class Reason {
  ColdBoot,
  Timer,
  IMU,
  HACommand,
  SonosFastPath,
  PostOTA,
};

constexpr const char* toString(Reason r) {
  switch (r) {
    case Reason::ColdBoot:       return "cold_boot";
    case Reason::Timer:          return "timer";
    case Reason::IMU:             return "imu";
    case Reason::HACommand:       return "ha_command";
    case Reason::SonosFastPath:   return "sonos_fast_path";
    case Reason::PostOTA:         return "post_ota";
  }
  return "unknown";
}

// Persisted across deep sleeps (RTC_SLOW memory on ESP32; ordinary globals on host).
struct Persisted {
  fw::modes::Mode current_mode = fw::modes::Mode::Unknown;
  int partial_refresh_count = 0;
  // Clock zone published by the renderer for `current_mode`, fetched on
  // every Full wake from `/display/:mode/clock-zone.json`. The partial
  // path reads (x, y) and looks up the matching baked Preset by
  // `font_size`. When `font_size == 0` no zone is known (cold boot or
  // the renderer has no clock-shaped DOM element for this mode) and the
  // partial path promotes to Full.
  int16_t  clock_zone_x = 0;
  int16_t  clock_zone_y = 0;
  uint16_t clock_zone_font_size = 0;
  // Zone width/height in panel-px (= u). Stored only when the renderer's
  // `/display/<mode>/clock-zone.json` includes `w` and `h` fields (which the
  // Night phrase clock uses for vertical centering — `clock_zone_h` is the
  // 220u flex container the bitmap centers inside). The digit-clock partial
  // path doesn't use these because it derives dimensions from the baked
  // Preset's font_size; zero is a safe sentinel for "not measured."
  uint16_t clock_zone_w = 0;
  uint16_t clock_zone_h = 0;
  // Last "HH:MM" the firmware drew (either via Full's seed or via a Partial).
  // The next Partial wake re-draws these digits first, runs a partialUpdate
  // (visually a no-op — those pixels are already black on the panel), and
  // that pulse seeds the library's `DMemoryNew` previous-frame buffer so the
  // SECOND partialUpdate's diff produces correct black-to-white "clear"
  // pulses for digit positions that the new minute no longer covers.
  // 0xff means "nothing drawn yet" — cold boot before first Full lands.
  uint8_t last_drawn_hh = 0xff;
  uint8_t last_drawn_mm = 0xff;
  // Night-mode phrase clock — the partial path uses pre-baked phrase
  // bitmaps (`fw::night_phrases::phraseForMinute`) keyed by min-of-day, so
  // the seed-then-draw pattern needs to remember the *minute of day* that
  // was last drawn (not the hh:mm tuple above, which encodes wall-clock
  // digits the digit-clock path uses). 0xffff means "nothing drawn yet";
  // the next partial's seed step uses the previously-drawn phrase bitmap
  // to seed the library's `DMemoryNew` buffer the same way the digit path
  // re-blits last_drawn_hh:mm. See add-night-text-clock-partials.
  uint16_t last_drawn_phrase_min = 0xffff;
  // FNV-32 of the last seen `inkplate/state/now_playing_track` payload.
  // Updated by `doFull` after a successful NowPlaying draw; checked by the
  // Poll handler to decide whether the current track has changed since
  // the last redraw. Zero is the "uninitialised" sentinel — the empty-
  // payload short-circuit guarantees we never store fnv32("").
  uint32_t sonos_track_hash = 0;
  // Mirror of HA's `input_text.inkplate_active_override == "now_playing"`.
  // Read on every Full/Poll wake from the retained MQTT topic
  // `inkplate/state/active_override`. While true, `pathForMinute` returns
  // Poll regardless of `current_mode` — keeps per-minute cadence through
  // tap-peeks, where active_mode briefly flips to a peek face but the
  // session is still active.
  bool session_now_playing = false;
};

Persisted& persisted();

// Host-test only: reset persisted state between scenarios.
void reset();

// Decide which wake sources to arm before the next sleep, based on the mode
// that will be resumed and the current wall-clock hour.
hal::WakeSourceMask armMask(fw::modes::Mode next_mode, int hour);

// -----------------------------------------------------------------------------
// Time-of-day wake schedule.
//
// The device wakes at minute-aligned boundaries, and which kind of wake each
// minute drives is decided by:
//   * the tier that the minute falls in (Night / Morning / Midday / Evening),
//   * the active mode (NowPlaying overrides everything to Full),
//   * cadence multiples within the tier.
//
// Wake taxonomy:
//   Full     — bring up WiFi+MQTT, fetch face PNG, full e-ink refresh,
//              publish device state.
//   Poll     — WiFi+MQTT only; read retained active_mode + schedule +
//              session-override topics. No e-ink. If the poll detects a
//              mode change (or, in NowPlaying, a track change), caller
//              promotes the wake to Full.
//   Partial  — no network. Render the clock zone locally from baked
//              glyphs and 1-bit partialUpdate(). Offline, ~0.06 mAh.
//   Skip     — wake fired but no work for this minute. Caller arms the
//              next wake and goes straight back to sleep.
//
// The planner consults the operator-edited schedule (one entry per tier)
// to decide which path each minute takes. Path priority within a tier is
// Full > Poll > Partial > Skip — a minute that's a multiple of multiple
// cadences resolves to the highest-priority hit. NowPlaying (or an active
// session-override) replaces every minute's path with Poll, with the Poll
// handler conditionally promoting to Full on actual content change.
//
// Tests in `firmware/test/scenarios/schedule_tests.cpp` cover each cadence
// case and boundary transition for the default schedule.
enum class Path { Full, Poll, Partial, Skip };

// `pathName` (not `toString`) so unqualified ADL inside doctest's
// `DOCTEST_STRINGIFY(toString(x))` macro does not bind here and short-circuit
// stringification with a `const char*` (which then breaks `String + char*`
// concatenation). Path stringification flows through `operator<<` instead.
constexpr const char* pathName(Path p) {
  switch (p) {
    case Path::Full:    return "full";
    case Path::Poll:    return "poll";
    case Path::Partial: return "partial";
    case Path::Skip:    return "skip";
  }
  return "unknown";
}

inline std::ostream& operator<<(std::ostream& os, Path p) { return os << pathName(p); }

struct WakePlan {
  Path path;
  // Number of WHOLE MINUTES from the current minute to the next non-Skip
  // wake. The caller converts to seconds, subtracts seconds-into-current-
  // minute and tick-elapsed, clamps to a sane minimum, and arms the timer.
  // Always ≥ 1 (NowPlaying always returns 1; tiers with sparse cadences may
  // return up to 14 in Night).
  int minutes_to_next_wake;
};

// One tier in the schedule. Eight bytes; four of these + the version/flags/
// hash header give a 40-byte Schedule struct that fits comfortably in RTC
// slow memory and serialises 1:1 to NVS.
struct TierEntry {
  uint16_t start_min;     // minute-of-day, 0..1439
  uint16_t full_min;      // 1..720
  uint16_t poll_min;      // 0..(full_min-1); 0 = no separate poll cadence
  uint16_t partial_min;   // 0..full_min; 0 = no partials in this tier
};
static_assert(sizeof(TierEntry) == 8, "TierEntry must be 8 bytes");

// The wake-time schedule. Tiers are stored ordered by `start_min`; the tier
// whose `start_min` is largest owns the wraparound segment from its start
// through midnight to tier[0].start_min the next day.
struct Schedule {
  uint8_t  version;       // == 1 when valid
  uint8_t  valid;         // 0 = not populated; 1 = valid
  uint16_t pad;
  uint32_t payload_hash;  // FNV-32 of the JSON payload that produced this
  TierEntry tiers[4];
};
static_assert(sizeof(Schedule) == 40, "Schedule must be 40 bytes");

// Source of the schedule used for this wake's planning, surfaced to the
// caller so the diag-ring flag bits can record where it came from.
enum class ScheduleSource {
  Cache,    // RTC slow-memory cache hit (steady-state warm wake)
  Nvs,     // RTC empty, NVS hit (cold-boot recovery)
  Default, // Both empty, fell through to kDefaultSchedule
};

struct ResolvedSchedule {
  Schedule schedule;
  ScheduleSource source;
};

// Compile-time default schedule, matching the today's hardcoded tier table.
// Used when neither RTC cache nor NVS has a valid entry — i.e. fresh-flash
// cold boot. Tiers stored in start-time order: Morning, Midday, Evening,
// Night (Night straddles midnight).
extern const Schedule kDefaultSchedule;

// Parse a JSON schedule payload from MQTT. Returns a Schedule with valid=1
// on success. On any parse / validation failure (malformed JSON, missing
// fields, out-of-range integer, divisibility / alignment violation,
// non-canonical tier name, duplicate tier, non-distinct starts), returns
// Schedule{} (valid=0); the failure reason is logged via FW_LOG so a bad
// operator edit shows up cleanly in serial output. Whitespace-tolerant;
// per-tier field lookups are scoped to that tier's `{...}` substring so a
// later tier's `full_min` cannot mask an earlier one. Empty input returns
// Schedule{} silently — the caller short-circuits before getting here.
Schedule parseSchedule(const std::string& json);

// FNV-32 over a byte payload. Used to dedup unchanged retained-MQTT reads
// without re-parsing, and exposed in `state/device` JSON as `schedule_hash`
// so HA can confirm pickup. Stable across calls and across builds.
uint32_t fnv32(const std::string& s);

// Resolve the schedule to use for this wake's path planning. Tries:
//   1. RTC slow-memory cache (`g_schedule_cache`).
//   2. NVS-persisted blob (namespace "inkplate", key "sched_v1").
//   3. Compile-time `kDefaultSchedule`.
// Falls through on empty / wrong-version / wrong-size at any layer. If a
// valid NVS blob is found while RTC is empty, the cache is repopulated as a
// side effect so subsequent wakes hit the cache.
ResolvedSchedule resolveSchedule();

// Variant for cold-boot wakes. Functionally identical today (RTC is wiped
// on cold boot so layer 1 always misses), but documents intent at the call
// site and gives a hook for future divergence (e.g., explicit NVS preload
// before any other initialization).
ResolvedSchedule resolveScheduleColdBoot();

// Persist a parsed schedule. Order of operations is **NVS first, then RTC**
// so a reset between the two writes loses RTC (wiped on cold boot anyway)
// but preserves the new schedule durably — the next cold boot reads NVS
// and repopulates RTC, no schedule loss. NVS write failure is logged but
// does not abort the RTC update; the schedule remains correct for the
// device's current uptime, only persistence is lost.
void applySchedule(const Schedule& parsed);

// Host-test only: clear the RTC cache and the host-stub NVS state.
void resetScheduleForTests();

// Host-test only: clear the RTC cache while leaving the NVS stand-in
// untouched. Models the cold-boot wipe (RTC slow memory loses its content
// across power loss / brown-out, but NVS in flash persists), so the Nvs
// fallback path is testable end-to-end.
void wipeScheduleCacheForTests();

// Pure function: given the current minute-of-day in local time (0..1439),
// the active mode, a resolved schedule, and the cached Now-Playing session
// flag, decide what kind of wake to do and how many minutes until the next
// non-Skip wake. No I/O, no globals — everything else is the caller's
// problem (network, draw, sleep arming).
//
// `local_min_of_day` must be in [0, 1440). Out-of-range values are clamped
// via modulo so the function never returns Skip with an undefined
// `minutes_to_next_wake`.
//
// `session_now_playing` is the canonical "Sonos session is active" state
// from HA's `input_text.inkplate_active_override`. While true, the
// override returns `Path::Poll` regardless of `mode` so a tap-peek
// (which briefly flips `mode` to a peek face) doesn't drop the device
// to tier cadence. The `mode == NowPlaying` clause inside `pathForMinute`
// is the cold-boot fallback used until the override topic has been read
// at least once.
WakePlan planWake(int local_min_of_day, fw::modes::Mode mode,
                  const Schedule& schedule,
                  bool session_now_playing = false);

}  // namespace fw::wake
