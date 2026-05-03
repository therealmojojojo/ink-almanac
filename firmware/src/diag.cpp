#include "diag.h"

#include <cstdio>
#include <cstring>

#ifdef ARDUINO
#include <esp_attr.h>
#endif

namespace fw::diag {

namespace {

#ifdef ARDUINO
RTC_DATA_ATTR Entry g_ring[kRingSize] = {};
RTC_DATA_ATTR uint32_t g_count = 0;
#else
Entry g_ring[kRingSize] = {};
uint32_t g_count = 0;
#endif

char reasonChar(uint8_t r) {
  // Mirrors fw::wake::Reason ordering: ColdBoot, Timer, IMU, HACommand,
  // SonosFastPath, PostOTA. Single-letter abbreviations chosen for readability
  // in the rendered ring, not for a stable on-wire protocol.
  switch (r) {
    case 0: return 'c';   // ColdBoot
    case 1: return 't';   // Timer
    case 2: return 'i';   // IMU
    case 3: return 'h';   // HACommand
    case 4: return 's';   // SonosFastPath
    case 5: return 'o';   // PostOTA
    default: return '?';
  }
}

char pathChar(uint8_t p) {
  // Mirrors fw::wake::Path: Full, Poll, Partial, PollPartial, Skip.
  // 0xff means "not planned" — used for cold-boot Fulls that bypass planWake.
  switch (p) {
    case 0:    return 'F';   // Full
    case 1:    return 'L';   // Poll
    case 2:    return 'P';   // Partial
    case 3:    return 'Q';   // PollPartial
    case 4:    return 'S';   // Skip
    case 0xff: return 'X';   // not planned
    default:   return '?';
  }
}

char modeChar(uint8_t m) {
  // Mirrors fw::modes::Mode. Best-effort one-letter abbreviation — the
  // rendered string is for human inspection, not parsing.
  switch (m) {
    case 0: return 'U';   // Unknown
    case 1: return 'S';   // Summary
    case 2: return 'W';   // Weather
    case 3: return 'G';   // Gallery
    case 4: return 'N';   // Night
    case 5: return 'Y';   // NowPlaying
    default: return '?';
  }
}

}  // namespace

void record(const Entry& e) {
  g_ring[g_count % kRingSize] = e;
  ++g_count;
}

uint32_t totalCount() { return g_count; }

void reset() {
  std::memset(static_cast<void*>(g_ring), 0, sizeof(g_ring));
  g_count = 0;
}

std::size_t format(char* buf, std::size_t n) {
  if (n == 0) return 0;
  std::size_t off = 0;

  // Header: total wake count. Lets the reader detect a missing wake (the
  // ring's wrap-around might hide a tick() that crashed before recording).
  int header = std::snprintf(buf + off, n - off, "n=%u", g_count);
  if (header < 0) { buf[0] = 0; return 0; }
  off += static_cast<std::size_t>(header);

  // Walk oldest → newest. The ring is full iff g_count >= kRingSize.
  const uint32_t start = g_count >= kRingSize ? g_count - kRingSize : 0;
  for (uint32_t i = start; i < g_count; ++i) {
    if (off + 1 >= n) break;
    const Entry& e = g_ring[i % kRingSize];
    // Each entry: " <epoch_low>,<rcRR><pPP><mMM><flagsX>[/<cycles>]"
    // - epoch_low: low 4 hex digits of the epoch (enough to distinguish
    //   wakes within ~18 hours; wraparound is fine, this is a debug log).
    // - flags: hex digit packing (wifi=1, mqtt=2, pg=4, drew=8, partial=16).
    int wrote = std::snprintf(
        buf + off, n - off,
        " %04x,%c%c%c%x",
        static_cast<unsigned>(e.epoch & 0xFFFF),
        reasonChar(e.reason), pathChar(e.path), modeChar(e.mode),
        static_cast<unsigned>(e.flags) & 0x1F);
    if (wrote < 0) break;
    off += static_cast<std::size_t>(wrote);
    if (e.cycles && off + 8 < n) {
      int extra = std::snprintf(buf + off, n - off, "/c%u",
                                static_cast<unsigned>(e.cycles));
      if (extra > 0) off += static_cast<std::size_t>(extra);
    }
    if (e.reset_reason && off + 6 < n) {
      // Only set on cold-boot entries — distinguishes brown-out (9),
      // task-WDT (6), int-WDT (5), panic (4), POR (1), external reset
      // (e.g., RTS pin → 2). Inspecting the trail of `cFU?/r9` over a
      // night tells us why the cold boots are happening.
      int extra = std::snprintf(buf + off, n - off, "/r%u",
                                static_cast<unsigned>(e.reset_reason));
      if (extra > 0) off += static_cast<std::size_t>(extra);
    }
    if (off >= n) break;
  }

  if (off >= n) off = n - 1;
  buf[off] = 0;
  return off;
}

}  // namespace fw::diag
