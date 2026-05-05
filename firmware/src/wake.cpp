#include "wake.h"

#include <algorithm>
#include <cstring>
#include <cstdio>

#ifdef ARDUINO
#include <Arduino.h>
#include <esp_attr.h>
#include <Preferences.h>
// Variadic-only form so call sites without extra args don't trip
// `-Wvariadic-macro-arguments-omitted` (the `##__VA_ARGS__` pattern is a
// GCC extension that clang flags as a C++20-only feature).
#define WAKE_LOG(...) (Serial.printf("[wake] " __VA_ARGS__), Serial.printf("\n"))
#else
#define WAKE_LOG(...) ((void)0)
#endif

#include "config.h"

namespace fw::wake {

#ifdef ARDUINO
// RTC slow memory survives deep sleep (but not power-off / reflash). Holding
// `current_mode` here lets the minute-tick early-return work: on a normal
// timer wake the resolved `active_mode` matches the stored one, no full
// refresh is scheduled, and the partial-refresh counter continues toward the
// ghost-clear threshold.
//
// `volatile` qualifier: documented ESP32 footgun where compiler optimization
// can elide reads/writes against RTC_DATA_ATTR storage despite the bootloader
// restoring values across deep-sleep wake. See ESP32 forum thread 9407 and
// flashgamer.com's "RTC memory on ESP32 and DeepSleep gotcha". Cheap insurance.
RTC_DATA_ATTR volatile Persisted g_persisted{};
RTC_DATA_ATTR volatile Schedule  g_schedule_cache{};
Persisted& persisted() { return const_cast<Persisted&>(g_persisted); }
#else
Persisted& persisted() {
  // Host sim: plain static. Scenarios reset state via `wake::reset()`.
  static Persisted p;
  return p;
}
#endif

// Host stand-ins for the RTC cache and NVS blob. On device the cache lives
// in RTC_DATA_ATTR storage above and NVS lives in flash; on host these are
// plain statics that scenarios reset between runs via
// `resetScheduleForTests()`.
namespace {
#ifndef ARDUINO
Schedule g_host_cache{};
bool     g_host_nvs_present = false;
Schedule g_host_nvs{};
#endif
}

// Mutable accessor for the RTC cache (device) or its host stand-in.
static Schedule& scheduleCache() {
#ifdef ARDUINO
  return const_cast<Schedule&>(g_schedule_cache);
#else
  return g_host_cache;
#endif
}

void reset() { persisted() = Persisted{}; }

void resetScheduleForTests() {
  scheduleCache() = Schedule{};
#ifndef ARDUINO
  g_host_nvs_present = false;
  g_host_nvs = Schedule{};
#endif
}

void wipeScheduleCacheForTests() {
  scheduleCache() = Schedule{};
}

// -----------------------------------------------------------------------------
// FNV-32 hash. Used to dedup retained-MQTT schedule reads without re-parsing
// and exposed in `state/device` JSON as the `schedule_hash` field so HA can
// confirm the device adopted a freshly-published schedule.

uint32_t fnv32(const std::string& s) {
  // FNV-1a, 32-bit.
  uint32_t h = 2166136261u;
  for (char c : s) {
    h ^= static_cast<uint32_t>(static_cast<unsigned char>(c));
    h *= 16777619u;
  }
  return h;
}

// -----------------------------------------------------------------------------
// Default schedule. Matches the prior hardcoded `tierFor()` table bit-for-bit
// so a fresh-flash boot pre-MQTT shows the same cadence the device shipped
// with. Tiers stored in start-time order: Morning, Midday, Evening, Night
// (Night straddles midnight and owns the wraparound segment).
const Schedule kDefaultSchedule = []() {
  Schedule s{};
  s.version = 1;
  s.valid = 1;
  s.payload_hash = 0;
  s.tiers[0] = TierEntry{ 6 * 60 + 30, 15, 3, 1 };  // Morning  06:30
  s.tiers[1] = TierEntry{10 * 60,      30, 0, 5 };  // Midday   10:00
  s.tiers[2] = TierEntry{17 * 60,      15, 3, 1 };  // Evening  17:00
  s.tiers[3] = TierEntry{22 * 60,      15, 0, 0 };  // Night    22:00
  return s;
}();

// -----------------------------------------------------------------------------
// Schedule planner. Pure arithmetic over the resolved Schedule's tier table.
// Tests: firmware/test/scenarios/schedule_tests.cpp,
//        firmware/test/scenarios/wake_schedule_plan_tests.cpp.

namespace {

// Find which tier owns `min_of_day`. Tiers are stored ordered by start_min;
// the largest-start tier wraps midnight and owns minutes < tiers[0].start_min.
int tierIndexFor(int min_of_day, const Schedule& s) {
  if (min_of_day < s.tiers[0].start_min) return 3;  // wrap into last tier
  for (int i = 0; i < 3; ++i) {
    if (min_of_day >= s.tiers[i].start_min &&
        min_of_day <  s.tiers[i + 1].start_min) {
      return i;
    }
  }
  return 3;  // min_of_day >= tiers[3].start_min
}

Path pathForMinute(int min_of_day, fw::modes::Mode mode, const Schedule& s,
                   bool session_now_playing) {
  // Now-Playing session override — keeps per-minute cadence through tap-peeks
  // and through the operator's "no daytime Polls" tier configurations. The
  // canonical signal is the session flag (mirror of HA's
  // `input_text.inkplate_active_override`); the `mode == NowPlaying` clause
  // is the cold-boot fallback for the window before the override topic has
  // been read for the first time.
  //
  // Returns Path::Poll (not Full): the Poll handler reads the retained
  // `inkplate/state/now_playing_track` topic and promotes to a Full only on
  // actual track change. Full-every-minute (the previous behavior) burned
  // ~300 mAh/hour during music for almost no benefit.
  if (session_now_playing || mode == fw::modes::Mode::NowPlaying) {
    return Path::Poll;
  }

  const TierEntry& t = s.tiers[tierIndexFor(min_of_day, s)];
  if (t.full_min    && (min_of_day % t.full_min)    == 0) return Path::Full;
  if (t.poll_min    && (min_of_day % t.poll_min)    == 0) return Path::Poll;
  if (t.partial_min && (min_of_day % t.partial_min) == 0) return Path::Partial;
  return Path::Skip;
}

}  // namespace

WakePlan planWake(int local_min_of_day, fw::modes::Mode mode,
                  const Schedule& schedule, bool session_now_playing) {
  // Normalize. Negative input would break the modulo; out-of-range positive
  // input wraps to today.
  int m = local_min_of_day % 1440;
  if (m < 0) m += 1440;

  const Schedule& s = schedule.valid ? schedule : kDefaultSchedule;
  const Path path = pathForMinute(m, mode, s, session_now_playing);

  // Find the next non-Skip minute. NowPlaying / session-active returns Poll
  // every minute so the loop exits immediately; even Night (sparsest cadence)
  // crosses a Full within 14 minutes.
  for (int delta = 1; delta <= 1440; ++delta) {
    const int n = (m + delta) % 1440;
    if (pathForMinute(n, mode, s, session_now_playing) != Path::Skip) {
      return {path, delta};
    }
  }

  // Unreachable — every tier has a non-zero full cadence so a Full minute
  // always exists within 24 h. Fall through with a safe default.
  return {path, 1};
}

// -----------------------------------------------------------------------------
// JSON parser. Hand-rolled, fixed schema, no library. Whitespace-tolerant;
// per-tier field lookups are scoped to a single tier's `{...}` substring;
// brace-matching is string-aware so a stray `{` or `}` inside a string field
// can't fool the depth counter.

namespace {

constexpr int kMinFull   = 1;
constexpr int kMaxFull   = 720;
constexpr int kInt16Max  = 32767;

struct Span { size_t lo; size_t hi; };  // half-open [lo, hi)

void skipWs(const std::string& s, size_t& i) {
  while (i < s.size()) {
    const char c = s[i];
    if (c == ' ' || c == '\t' || c == '\n' || c == '\r') ++i;
    else break;
  }
}

// Advance `i` past a JSON string starting at the opening `"`. Returns true
// on a well-formed close and updates `i` to one past the closing `"`. False
// on unterminated. Handles `\"` and other JSON escapes by skipping the
// escaped byte; we don't need to decode them, only to keep braces inside
// strings out of the depth counter.
bool skipString(const std::string& s, size_t& i) {
  if (i >= s.size() || s[i] != '"') return false;
  ++i;
  while (i < s.size()) {
    const char c = s[i];
    if (c == '\\') {
      i += 2;
      continue;
    }
    if (c == '"') { ++i; return true; }
    ++i;
  }
  return false;
}

// Find the brace-matched extent of a JSON object starting at `lo` (which
// must point at the opening `{`). Returns the span [lo, end) where `end` is
// one past the closing `}`. On malformed input returns {0, 0}. Skips strings
// to avoid being fooled by `{` / `}` inside them.
Span objectSpan(const std::string& s, size_t lo) {
  if (lo >= s.size() || s[lo] != '{') return {0, 0};
  size_t i = lo;
  int depth = 0;
  while (i < s.size()) {
    const char c = s[i];
    if (c == '"') {
      if (!skipString(s, i)) return {0, 0};
      continue;
    }
    if (c == '{') { ++depth; ++i; continue; }
    if (c == '}') {
      --depth;
      ++i;
      if (depth == 0) return {lo, i};
      continue;
    }
    ++i;
  }
  return {0, 0};
}

// Find the position immediately after `"key"\s*:` within scope [scope_lo,
// scope_hi). Returns std::string::npos on miss. Whitespace-tolerant.
size_t findKeyValueStart(const std::string& s, size_t scope_lo, size_t scope_hi,
                         const char* key) {
  const std::string needle = std::string("\"") + key + "\"";
  size_t i = scope_lo;
  while (i + needle.size() <= scope_hi) {
    auto pos = s.find(needle, i);
    if (pos == std::string::npos || pos + needle.size() > scope_hi) {
      return std::string::npos;
    }

    // Reject a needle hit that lives inside another string literal.
    bool in_string = false;
    for (size_t j = scope_lo; j < pos; ++j) {
      if (s[j] == '\\' && in_string) { ++j; continue; }
      if (s[j] == '"') in_string = !in_string;
    }
    if (in_string) { i = pos + 1; continue; }

    size_t after = pos + needle.size();
    skipWs(s, after);
    if (after >= scope_hi || s[after] != ':') { i = pos + 1; continue; }
    ++after;
    skipWs(s, after);
    if (after >= scope_hi) return std::string::npos;
    return after;
  }
  return std::string::npos;
}

// Parse a non-negative integer from `s[start..scope_hi)`. Rejects negatives,
// non-digits, empty, and overflow > INT16_MAX.
bool parseUintField(const std::string& s, size_t start, size_t scope_hi,
                    int* out) {
  if (start >= scope_hi) return false;
  if (s[start] == '-') return false;
  long long v = 0;
  bool any = false;
  size_t i = start;
  while (i < scope_hi && s[i] >= '0' && s[i] <= '9') {
    v = v * 10 + (s[i] - '0');
    if (v > kInt16Max) return false;
    ++i;
    any = true;
  }
  if (!any) return false;
  *out = static_cast<int>(v);
  return true;
}

// Parse a quoted string field (opening quote at `start`). Writes the
// unescaped contents to `*out` (limited to 16 chars; longer strings reject
// — sufficient for tier names and HH:MM times). Rejects backslash escapes:
// none of the canonical fields need them, and a payload that includes them
// is suspicious enough to fail fast.
bool parseStringField(const std::string& s, size_t start, size_t scope_hi,
                      std::string* out) {
  if (start >= scope_hi || s[start] != '"') return false;
  size_t i = start + 1;
  out->clear();
  while (i < scope_hi) {
    const char c = s[i];
    if (c == '"') return true;
    if (c == '\\') return false;
    if (out->size() >= 16) return false;
    out->push_back(c);
    ++i;
  }
  return false;
}

bool parseHhMm(const std::string& s, int* out) {
  if (s.size() != 5 || s[2] != ':') return false;
  if (s[0] < '0' || s[0] > '9') return false;
  if (s[1] < '0' || s[1] > '9') return false;
  if (s[3] < '0' || s[3] > '9') return false;
  if (s[4] < '0' || s[4] > '9') return false;
  const int h = (s[0] - '0') * 10 + (s[1] - '0');
  const int m = (s[3] - '0') * 10 + (s[4] - '0');
  if (h > 23 || m > 59) return false;
  *out = h * 60 + m;
  return true;
}

int tierNameIndex(const std::string& name) {
  if (name == "night")   return 0;
  if (name == "morning") return 1;
  if (name == "midday")  return 2;
  if (name == "evening") return 3;
  return -1;
}

bool parseOneTier(const std::string& s, Span scope, TierEntry* out_entry,
                  int* out_name_index) {
  size_t pos = findKeyValueStart(s, scope.lo, scope.hi, "name");
  if (pos == std::string::npos) { WAKE_LOG("parse: tier missing name"); return false; }
  std::string name;
  if (!parseStringField(s, pos, scope.hi, &name)) {
    WAKE_LOG("parse: tier name not a clean string");
    return false;
  }
  const int ni = tierNameIndex(name);
  if (ni < 0) { WAKE_LOG("parse: tier name not in canonical set"); return false; }
  *out_name_index = ni;

  pos = findKeyValueStart(s, scope.lo, scope.hi, "start");
  if (pos == std::string::npos) { WAKE_LOG("parse: tier missing start"); return false; }
  std::string start_str;
  if (!parseStringField(s, pos, scope.hi, &start_str)) {
    WAKE_LOG("parse: tier start not a clean string");
    return false;
  }
  int start_min = 0;
  if (!parseHhMm(start_str, &start_min)) {
    WAKE_LOG("parse: tier start not HH:MM");
    return false;
  }

  int full_min = 0, poll_min = 0, partial_min = 0;
  pos = findKeyValueStart(s, scope.lo, scope.hi, "full_min");
  if (pos == std::string::npos || !parseUintField(s, pos, scope.hi, &full_min)) {
    WAKE_LOG("parse: tier full_min missing or invalid");
    return false;
  }
  pos = findKeyValueStart(s, scope.lo, scope.hi, "poll_min");
  if (pos == std::string::npos || !parseUintField(s, pos, scope.hi, &poll_min)) {
    WAKE_LOG("parse: tier poll_min missing or invalid");
    return false;
  }
  pos = findKeyValueStart(s, scope.lo, scope.hi, "partial_min");
  if (pos == std::string::npos || !parseUintField(s, pos, scope.hi, &partial_min)) {
    WAKE_LOG("parse: tier partial_min missing or invalid");
    return false;
  }

  if (full_min < kMinFull || full_min > kMaxFull) {
    WAKE_LOG("parse: full_min out of [1,720]: %d", full_min);
    return false;
  }
  if (poll_min > 0 && poll_min >= full_min) {
    WAKE_LOG("parse: poll_min must be < full_min: poll=%d full=%d", poll_min, full_min);
    return false;
  }
  if (partial_min > full_min) {
    WAKE_LOG("parse: partial_min must be <= full_min: partial=%d full=%d",
             partial_min, full_min);
    return false;
  }
  if (poll_min > 0 && (full_min % poll_min) != 0) {
    WAKE_LOG("parse: full_min %% poll_min != 0: full=%d poll=%d", full_min, poll_min);
    return false;
  }
  if (partial_min > 0 && (full_min % partial_min) != 0) {
    WAKE_LOG("parse: full_min %% partial_min != 0: full=%d partial=%d",
             full_min, partial_min);
    return false;
  }
  if ((start_min % full_min) != 0) {
    WAKE_LOG("parse: start_min %% full_min != 0 (alignment): start=%d full=%d",
             start_min, full_min);
    return false;
  }

  out_entry->start_min   = static_cast<uint16_t>(start_min);
  out_entry->full_min    = static_cast<uint16_t>(full_min);
  out_entry->poll_min    = static_cast<uint16_t>(poll_min);
  out_entry->partial_min = static_cast<uint16_t>(partial_min);
  return true;
}

}  // namespace

Schedule parseSchedule(const std::string& json) {
  Schedule fail{};

  if (json.empty()) {
    return fail;
  }

  size_t vpos = findKeyValueStart(json, 0, json.size(), "version");
  if (vpos == std::string::npos) {
    WAKE_LOG("parse: missing version");
    return fail;
  }
  int version = 0;
  if (!parseUintField(json, vpos, json.size(), &version)) {
    WAKE_LOG("parse: version not an integer");
    return fail;
  }
  if (version != 1) {
    WAKE_LOG("parse: unsupported version %d", version);
    return fail;
  }

  size_t tpos = findKeyValueStart(json, 0, json.size(), "tiers");
  if (tpos == std::string::npos) {
    WAKE_LOG("parse: missing tiers array");
    return fail;
  }
  if (tpos >= json.size() || json[tpos] != '[') {
    WAKE_LOG("parse: tiers value is not an array");
    return fail;
  }

  TierEntry tiers[4]{};
  int names_seen[4] = {0, 0, 0, 0};
  int count = 0;
  size_t i = tpos + 1;
  skipWs(json, i);
  while (i < json.size() && json[i] != ']') {
    if (json[i] != '{') {
      WAKE_LOG("parse: tiers array element is not an object");
      return fail;
    }
    if (count >= 4) {
      WAKE_LOG("parse: more than 4 tiers");
      return fail;
    }
    Span obj = objectSpan(json, i);
    if (obj.lo == 0 && obj.hi == 0) {
      WAKE_LOG("parse: malformed tier object");
      return fail;
    }
    int name_index = -1;
    TierEntry te{};
    Span scope{obj.lo + 1, obj.hi - 1};
    if (!parseOneTier(json, scope, &te, &name_index)) return fail;
    if (names_seen[name_index] != 0) {
      WAKE_LOG("parse: duplicate tier name index=%d", name_index);
      return fail;
    }
    names_seen[name_index] = 1;
    tiers[count++] = te;

    i = obj.hi;
    skipWs(json, i);
    if (i < json.size() && json[i] == ',') { ++i; skipWs(json, i); }
  }
  if (count != 4) {
    WAKE_LOG("parse: expected exactly 4 tiers, got %d", count);
    return fail;
  }
  for (int k = 0; k < 4; ++k) {
    if (!names_seen[k]) {
      WAKE_LOG("parse: missing canonical tier name index=%d", k);
      return fail;
    }
  }

  std::sort(tiers, tiers + 4,
            [](const TierEntry& a, const TierEntry& b) {
              return a.start_min < b.start_min;
            });

  for (int k = 1; k < 4; ++k) {
    if (tiers[k].start_min == tiers[k - 1].start_min) {
      WAKE_LOG("parse: duplicate tier start_min=%u", tiers[k].start_min);
      return fail;
    }
  }

  Schedule out{};
  out.version = 1;
  out.valid = 1;
  out.payload_hash = 0;  // caller fills in from the raw payload
  for (int k = 0; k < 4; ++k) out.tiers[k] = tiers[k];
  return out;
}

// -----------------------------------------------------------------------------
// NVS layer. ARDUINO uses Preferences (the Arduino-ESP32 wrapper around the
// ESP-IDF NVS API); host build uses an in-process static so persistence-flow
// tests can exercise the same fall-through chain without a real flash.

namespace {

#ifdef ARDUINO
constexpr const char* kNvsNs  = "inkplate";
constexpr const char* kNvsKey = "sched_v1";
#endif

bool nvsRead(Schedule* out) {
#ifdef ARDUINO
  Preferences p;
  if (!p.begin(kNvsNs, /*readOnly=*/true)) {
    return false;
  }
  const size_t got = p.getBytesLength(kNvsKey);
  if (got != sizeof(Schedule)) {
    p.end();
    return false;
  }
  Schedule tmp{};
  const size_t read = p.getBytes(kNvsKey, &tmp, sizeof(Schedule));
  p.end();
  if (read != sizeof(Schedule)) return false;
  if (tmp.version != 1 || tmp.valid != 1) return false;
  *out = tmp;
  return true;
#else
  if (!g_host_nvs_present) return false;
  if (g_host_nvs.version != 1 || g_host_nvs.valid != 1) return false;
  *out = g_host_nvs;
  return true;
#endif
}

bool nvsWrite(const Schedule& s) {
#ifdef ARDUINO
  Preferences p;
  if (!p.begin(kNvsNs, /*readOnly=*/false)) {
    WAKE_LOG("nvs: begin(rw) failed");
    return false;
  }
  const size_t wrote = p.putBytes(kNvsKey, &s, sizeof(Schedule));
  p.end();
  if (wrote != sizeof(Schedule)) {
    WAKE_LOG("nvs: putBytes wrote %u of %u", static_cast<unsigned>(wrote),
             static_cast<unsigned>(sizeof(Schedule)));
    return false;
  }
  return true;
#else
  g_host_nvs = s;
  g_host_nvs_present = true;
  return true;
#endif
}

}  // namespace

ResolvedSchedule resolveSchedule() {
  Schedule& cache = scheduleCache();
  if (cache.valid == 1 && cache.version == 1) {
    Schedule snap{};
    std::memcpy(&snap, const_cast<const Schedule*>(&cache), sizeof(Schedule));
    return {snap, ScheduleSource::Cache};
  }
  Schedule from_nvs{};
  if (nvsRead(&from_nvs)) {
    cache = from_nvs;
    return {from_nvs, ScheduleSource::Nvs};
  }
  return {kDefaultSchedule, ScheduleSource::Default};
}

ResolvedSchedule resolveScheduleColdBoot() {
  // RTC is wiped on cold boot, so this is functionally identical to
  // resolveSchedule(). Distinct entry point so the call site reads
  // intentionally and we can diverge later (e.g., explicit NVS preload
  // before any other initialization).
  return resolveSchedule();
}

void applySchedule(const Schedule& parsed) {
  if (parsed.valid != 1 || parsed.version != 1) return;
  // NVS first so a reset between the two writes does not lose the change:
  // RTC is cold-boot-volatile anyway, but NVS persists through brown-out.
  if (!nvsWrite(parsed)) {
    WAKE_LOG("apply: nvs write failed; updating RTC anyway");
  }
  scheduleCache() = parsed;
}

// -----------------------------------------------------------------------------

hal::WakeSourceMask armMask(fw::modes::Mode next_mode, int hour) {
  using namespace fw::config;
  hal::WakeSourceMask mask = 0;

  // Timer wake whenever the mode has one.
  if (fw::modes::timerSeconds(next_mode) > 0) {
    mask |= static_cast<hal::WakeSourceMask>(hal::WakeSource::Timer);
  }

  // IMU INT is always armed so the device responds to taps at all times.
  mask |= static_cast<hal::WakeSourceMask>(hal::WakeSource::IMU);

  // Sonos fast-path: during Sonos window, a shorter timer replaces the mode timer
  // for fast-path wake. Encoded implicitly via the caller passing kSonosFastPathSec.
  (void)kSonosFastPathSec;

  // `hour` is unused now that PIR quiet-hours arming moved to HA. Keep the
  // parameter so callers don't change; silence the warning.
  (void)hour;

  return mask;
}

}  // namespace fw::wake
