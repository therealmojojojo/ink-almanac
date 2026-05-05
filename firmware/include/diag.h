#pragma once

// Diagnostic ring buffer in RTC slow memory.
//
// Records a compact summary of every wake so we can correlate a panel
// wedge with the sequence of preceding wakes. The ring lives in
// RTC_DATA_ATTR storage — survives deep sleep but not LiPo removal. That
// matches the failure mode: wakes lead up to the wedge, MQTT keeps
// publishing during the wedge (we observed this), so HA's last copy of
// `state/device` carries the ring contents from before and during the
// stuck period. Operator inspects the retained payload after recovery.
//
// Per-entry storage: 12 bytes. 32-entry ring = 384 B in RTC slow memory.
// Out of an 8 KB budget that's negligible.
//
// Encoding for MQTT: `format()` writes a compact text rendering — one
// space-separated token per entry, oldest first, suitable for embedding
// in the existing `state/device` JSON as a single string field.

#include <cstddef>
#include <cstdint>

namespace fw::diag {

struct Entry {
  uint32_t epoch;        // unix epoch when the wake started
  uint8_t reason;        // fw::wake::Reason as uint8
  uint8_t path;          // fw::wake::Path as uint8 (0xff = not planned, e.g. cold-boot Full)
  uint8_t mode;          // fw::modes::Mode as uint8
  uint8_t flags;         // bit0=wifi, bit1=mqtt, bit2=epd_pwrgood, bit3=draw_succeeded,
                         // bit4=partial_succeeded, bit5=schedule_loaded_from_cache,
                         // bit6=schedule_loaded_from_nvs, bit7=reserved.
                         // bits 5/6 are mutually exclusive within a single
                         // tick. Absence of both on a wake that brought MQTT
                         // up means the device ran on the baked default for
                         // this wake; "schedule changed during this wake" is
                         // detected via the schedule_hash field on
                         // inkplate/state/device transitioning, not via a
                         // per-wake flag bit.
  uint16_t cycles;       // partialUpdate1Bit() cycles (>0 means panel was driven)
  uint8_t reset_reason;  // ESP-IDF esp_reset_reason_t enum int. Populated
                         // only on ColdBoot wakes (1=POWERON, 2=EXT,
                         // 4=PANIC, 5=INT_WDT, 6=TASK_WDT, 9=BROWNOUT, …).
                         // 0 = not a cold boot or not on ARDUINO.
  uint8_t pad;
};
static_assert(sizeof(Entry) == 12, "DiagEntry must be 12 bytes");

constexpr size_t kRingSize = 32;

// Append an entry to the ring (oldest entry overwritten). Persists across
// deep sleep on device; on host sim, in-process static for assertions.
void record(const Entry& e);

// Total entries written since last LiPo removal. Lets the operator see
// "ring covers wakes N-31..N" without ambiguity about wraparound.
uint32_t totalCount();

// Render the ring as a compact text string into `buf` (size `n`). Returns
// the number of characters written (excluding the trailing NUL). Format:
//
//   "<count> [E:wake mode flags cycles] ..."
//
// Where each entry is `<epoch_low>,<reason_char><path_char><mode_char><flags_hex>[,c<N>]`.
// Designed to fit ~32 entries in ~900 characters.
std::size_t format(char* buf, std::size_t n);

// Host-test only: clear the ring and counter between scenarios.
void reset();

}  // namespace fw::diag
