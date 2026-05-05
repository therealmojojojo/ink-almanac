// Schedule JSON parser tests. The parser lives in fw::wake::parseSchedule()
// and is the chokepoint that protects the device from a malformed or hostile
// retained MQTT payload. These tests exercise:
//
//   - Happy-path JSON in compact and pretty-printed forms
//   - Whitespace tolerance around colons and inside objects
//   - Per-tier substring scoping (so tier 1's full_min can't mask tier 0's)
//   - Every individual rejection path: bounds, divisibility, alignment,
//     duplicate / missing tier names, tier count off-by-one, malformed
//     numbers, integer overflow, escaped strings, version mismatches.

#include <string>

#include "doctest.h"
#include "wake.h"

using fw::wake::parseSchedule;

namespace {

constexpr int hm(int h, int m) { return h * 60 + m; }

// Canonical default-schedule JSON, formatted compactly (one line). Kept in
// one place so divergence checks (e.g., "this payload that differs by ONE
// field rejects") are minimal-edit copies of this template.
const char* kCompactDefault =
    "{\"version\":1,"
    "\"tiers\":["
    "{\"name\":\"night\",\"start\":\"22:00\",\"full_min\":15,\"poll_min\":0,\"partial_min\":0},"
    "{\"name\":\"morning\",\"start\":\"06:30\",\"full_min\":15,\"poll_min\":3,\"partial_min\":1},"
    "{\"name\":\"midday\",\"start\":\"10:00\",\"full_min\":30,\"poll_min\":0,\"partial_min\":5},"
    "{\"name\":\"evening\",\"start\":\"17:00\",\"full_min\":15,\"poll_min\":3,\"partial_min\":1}"
    "]}";

}  // namespace

TEST_CASE("happy path: compact JSON parses into the four canonical tiers") {
  const auto s = parseSchedule(kCompactDefault);
  REQUIRE(s.valid == 1);
  CHECK(s.version == 1);
  // Sorted by start_min: morning(390), midday(600), evening(1020), night(1320).
  CHECK(s.tiers[0].start_min == hm(6, 30));
  CHECK(s.tiers[0].full_min == 15);
  CHECK(s.tiers[0].poll_min == 3);
  CHECK(s.tiers[0].partial_min == 1);
  CHECK(s.tiers[1].start_min == hm(10, 0));
  CHECK(s.tiers[1].full_min == 30);
  CHECK(s.tiers[1].poll_min == 0);
  CHECK(s.tiers[1].partial_min == 5);
  CHECK(s.tiers[2].start_min == hm(17, 0));
  CHECK(s.tiers[3].start_min == hm(22, 0));
}

TEST_CASE("happy path: pretty-printed multi-line JSON parses identically") {
  const std::string pretty =
      "{\n"
      "  \"version\" : 1,\n"
      "  \"tiers\" : [\n"
      "    { \"name\" : \"night\",   \"start\" : \"22:00\", \"full_min\" : 15, \"poll_min\" : 0, \"partial_min\" : 0 },\n"
      "    { \"name\" : \"morning\", \"start\" : \"06:30\", \"full_min\" : 15, \"poll_min\" : 3, \"partial_min\" : 1 },\n"
      "    { \"name\" : \"midday\",  \"start\" : \"10:00\", \"full_min\" : 30, \"poll_min\" : 0, \"partial_min\" : 5 },\n"
      "    { \"name\" : \"evening\", \"start\" : \"17:00\", \"full_min\" : 15, \"poll_min\" : 3, \"partial_min\" : 1 }\n"
      "  ]\n"
      "}\n";
  const auto a = parseSchedule(pretty);
  const auto b = parseSchedule(kCompactDefault);
  REQUIRE(a.valid == 1);
  REQUIRE(b.valid == 1);
  for (int i = 0; i < 4; ++i) {
    CHECK(a.tiers[i].start_min == b.tiers[i].start_min);
    CHECK(a.tiers[i].full_min == b.tiers[i].full_min);
    CHECK(a.tiers[i].poll_min == b.tiers[i].poll_min);
    CHECK(a.tiers[i].partial_min == b.tiers[i].partial_min);
  }
}

TEST_CASE("tiers in non-canonical order still sort correctly") {
  // Same tiers as kCompactDefault but listed evening-first. The parser sorts
  // by start_min, so the result must be identical.
  const char* j =
      "{\"version\":1,\"tiers\":["
      "{\"name\":\"evening\",\"start\":\"17:00\",\"full_min\":15,\"poll_min\":3,\"partial_min\":1},"
      "{\"name\":\"morning\",\"start\":\"06:30\",\"full_min\":15,\"poll_min\":3,\"partial_min\":1},"
      "{\"name\":\"night\",\"start\":\"22:00\",\"full_min\":15,\"poll_min\":0,\"partial_min\":0},"
      "{\"name\":\"midday\",\"start\":\"10:00\",\"full_min\":30,\"poll_min\":0,\"partial_min\":5}"
      "]}";
  const auto s = parseSchedule(j);
  REQUIRE(s.valid == 1);
  CHECK(s.tiers[0].start_min == hm(6, 30));
  CHECK(s.tiers[1].start_min == hm(10, 0));
  CHECK(s.tiers[2].start_min == hm(17, 0));
  CHECK(s.tiers[3].start_min == hm(22, 0));
}

TEST_CASE("per-tier scoping: outer full_min cannot mask a tier's value") {
  // Tier 0 (night) declares full_min=15; the parser must scope its lookup
  // for tier 1's full_min to tier 1's `{...}`, so tier 1 sees 30 (its own
  // value), not 15 (the first one in the document). Construct a payload
  // where naive un-scoped findKey would return tier 0's value.
  const char* j =
      "{\"version\":1,\"tiers\":["
      "{\"name\":\"night\",\"start\":\"22:00\",\"full_min\":15,\"poll_min\":0,\"partial_min\":0},"
      "{\"name\":\"midday\",\"start\":\"10:00\",\"full_min\":30,\"poll_min\":0,\"partial_min\":5},"
      "{\"name\":\"morning\",\"start\":\"06:30\",\"full_min\":15,\"poll_min\":3,\"partial_min\":1},"
      "{\"name\":\"evening\",\"start\":\"17:00\",\"full_min\":15,\"poll_min\":3,\"partial_min\":1}"
      "]}";
  const auto s = parseSchedule(j);
  REQUIRE(s.valid == 1);
  // After sort: morning, midday, evening, night.
  CHECK(s.tiers[1].start_min == hm(10, 0));
  CHECK(s.tiers[1].full_min == 30);  // midday: 30, NOT night's 15
}

// -----------------------------------------------------------------------------
// Defensive rejections.

TEST_CASE("empty payload returns invalid (caller short-circuits)") {
  const auto s = parseSchedule("");
  CHECK(s.valid == 0);
}

TEST_CASE("missing version is rejected") {
  const char* j = "{\"tiers\":[]}";
  CHECK(parseSchedule(j).valid == 0);
}

TEST_CASE("wrong version is rejected") {
  const std::string j =
      std::string("{\"version\":2,\"tiers\":[]}");
  CHECK(parseSchedule(j).valid == 0);
}

TEST_CASE("non-integer version is rejected") {
  const char* j = "{\"version\":\"1\",\"tiers\":[]}";
  CHECK(parseSchedule(j).valid == 0);
}

TEST_CASE("tiers value not an array is rejected") {
  const char* j = "{\"version\":1,\"tiers\":42}";
  CHECK(parseSchedule(j).valid == 0);
}

TEST_CASE("only 3 tiers is rejected") {
  const char* j =
      "{\"version\":1,\"tiers\":["
      "{\"name\":\"night\",\"start\":\"22:00\",\"full_min\":15,\"poll_min\":0,\"partial_min\":0},"
      "{\"name\":\"morning\",\"start\":\"06:30\",\"full_min\":15,\"poll_min\":3,\"partial_min\":1},"
      "{\"name\":\"midday\",\"start\":\"10:00\",\"full_min\":30,\"poll_min\":0,\"partial_min\":5}"
      "]}";
  CHECK(parseSchedule(j).valid == 0);
}

TEST_CASE("5 tiers is rejected") {
  const char* j =
      "{\"version\":1,\"tiers\":["
      "{\"name\":\"night\",\"start\":\"22:00\",\"full_min\":15,\"poll_min\":0,\"partial_min\":0},"
      "{\"name\":\"morning\",\"start\":\"06:30\",\"full_min\":15,\"poll_min\":3,\"partial_min\":1},"
      "{\"name\":\"midday\",\"start\":\"10:00\",\"full_min\":30,\"poll_min\":0,\"partial_min\":5},"
      "{\"name\":\"evening\",\"start\":\"17:00\",\"full_min\":15,\"poll_min\":3,\"partial_min\":1},"
      "{\"name\":\"morning\",\"start\":\"06:31\",\"full_min\":1,\"poll_min\":0,\"partial_min\":0}"
      "]}";
  CHECK(parseSchedule(j).valid == 0);
}

TEST_CASE("unknown tier name is rejected") {
  const char* j =
      "{\"version\":1,\"tiers\":["
      "{\"name\":\"dawn\",\"start\":\"05:00\",\"full_min\":15,\"poll_min\":0,\"partial_min\":0},"
      "{\"name\":\"morning\",\"start\":\"06:30\",\"full_min\":15,\"poll_min\":3,\"partial_min\":1},"
      "{\"name\":\"midday\",\"start\":\"10:00\",\"full_min\":30,\"poll_min\":0,\"partial_min\":5},"
      "{\"name\":\"evening\",\"start\":\"17:00\",\"full_min\":15,\"poll_min\":3,\"partial_min\":1}"
      "]}";
  CHECK(parseSchedule(j).valid == 0);
}

TEST_CASE("duplicate tier name is rejected") {
  const char* j =
      "{\"version\":1,\"tiers\":["
      "{\"name\":\"night\",\"start\":\"22:00\",\"full_min\":15,\"poll_min\":0,\"partial_min\":0},"
      "{\"name\":\"morning\",\"start\":\"06:30\",\"full_min\":15,\"poll_min\":3,\"partial_min\":1},"
      "{\"name\":\"morning\",\"start\":\"10:00\",\"full_min\":30,\"poll_min\":0,\"partial_min\":5},"
      "{\"name\":\"evening\",\"start\":\"17:00\",\"full_min\":15,\"poll_min\":3,\"partial_min\":1}"
      "]}";
  CHECK(parseSchedule(j).valid == 0);
}

TEST_CASE("non-monotone starts (duplicate start_min) is rejected") {
  const char* j =
      "{\"version\":1,\"tiers\":["
      "{\"name\":\"night\",\"start\":\"22:00\",\"full_min\":15,\"poll_min\":0,\"partial_min\":0},"
      "{\"name\":\"morning\",\"start\":\"06:30\",\"full_min\":15,\"poll_min\":3,\"partial_min\":1},"
      "{\"name\":\"midday\",\"start\":\"06:30\",\"full_min\":30,\"poll_min\":0,\"partial_min\":5},"
      "{\"name\":\"evening\",\"start\":\"17:00\",\"full_min\":15,\"poll_min\":3,\"partial_min\":1}"
      "]}";
  CHECK(parseSchedule(j).valid == 0);
}

TEST_CASE("full_min == 0 is rejected") {
  const char* j =
      "{\"version\":1,\"tiers\":["
      "{\"name\":\"night\",\"start\":\"22:00\",\"full_min\":0,\"poll_min\":0,\"partial_min\":0},"
      "{\"name\":\"morning\",\"start\":\"06:30\",\"full_min\":15,\"poll_min\":3,\"partial_min\":1},"
      "{\"name\":\"midday\",\"start\":\"10:00\",\"full_min\":30,\"poll_min\":0,\"partial_min\":5},"
      "{\"name\":\"evening\",\"start\":\"17:00\",\"full_min\":15,\"poll_min\":3,\"partial_min\":1}"
      "]}";
  CHECK(parseSchedule(j).valid == 0);
}

TEST_CASE("full_min > 720 is rejected") {
  const char* j =
      "{\"version\":1,\"tiers\":["
      "{\"name\":\"night\",\"start\":\"22:00\",\"full_min\":721,\"poll_min\":0,\"partial_min\":0},"
      "{\"name\":\"morning\",\"start\":\"06:30\",\"full_min\":15,\"poll_min\":3,\"partial_min\":1},"
      "{\"name\":\"midday\",\"start\":\"10:00\",\"full_min\":30,\"poll_min\":0,\"partial_min\":5},"
      "{\"name\":\"evening\",\"start\":\"17:00\",\"full_min\":15,\"poll_min\":3,\"partial_min\":1}"
      "]}";
  CHECK(parseSchedule(j).valid == 0);
}

TEST_CASE("poll_min >= full_min is rejected") {
  const char* j =
      "{\"version\":1,\"tiers\":["
      "{\"name\":\"night\",\"start\":\"22:00\",\"full_min\":15,\"poll_min\":0,\"partial_min\":0},"
      "{\"name\":\"morning\",\"start\":\"06:30\",\"full_min\":15,\"poll_min\":15,\"partial_min\":1},"
      "{\"name\":\"midday\",\"start\":\"10:00\",\"full_min\":30,\"poll_min\":0,\"partial_min\":5},"
      "{\"name\":\"evening\",\"start\":\"17:00\",\"full_min\":15,\"poll_min\":3,\"partial_min\":1}"
      "]}";
  CHECK(parseSchedule(j).valid == 0);
}

TEST_CASE("partial_min > full_min is rejected") {
  const char* j =
      "{\"version\":1,\"tiers\":["
      "{\"name\":\"night\",\"start\":\"22:00\",\"full_min\":15,\"poll_min\":0,\"partial_min\":0},"
      "{\"name\":\"morning\",\"start\":\"06:30\",\"full_min\":15,\"poll_min\":3,\"partial_min\":16},"
      "{\"name\":\"midday\",\"start\":\"10:00\",\"full_min\":30,\"poll_min\":0,\"partial_min\":5},"
      "{\"name\":\"evening\",\"start\":\"17:00\",\"full_min\":15,\"poll_min\":3,\"partial_min\":1}"
      "]}";
  CHECK(parseSchedule(j).valid == 0);
}

TEST_CASE("non-divisible cadence (full % poll != 0) is rejected") {
  const char* j =
      "{\"version\":1,\"tiers\":["
      "{\"name\":\"night\",\"start\":\"22:00\",\"full_min\":15,\"poll_min\":0,\"partial_min\":0},"
      "{\"name\":\"morning\",\"start\":\"06:30\",\"full_min\":15,\"poll_min\":4,\"partial_min\":1},"  // 15 % 4 = 3
      "{\"name\":\"midday\",\"start\":\"10:00\",\"full_min\":30,\"poll_min\":0,\"partial_min\":5},"
      "{\"name\":\"evening\",\"start\":\"17:00\",\"full_min\":15,\"poll_min\":3,\"partial_min\":1}"
      "]}";
  CHECK(parseSchedule(j).valid == 0);
}

TEST_CASE("non-divisible cadence (full % partial != 0) is rejected") {
  const char* j =
      "{\"version\":1,\"tiers\":["
      "{\"name\":\"night\",\"start\":\"22:00\",\"full_min\":15,\"poll_min\":0,\"partial_min\":0},"
      "{\"name\":\"morning\",\"start\":\"06:30\",\"full_min\":15,\"poll_min\":3,\"partial_min\":2},"  // 15 % 2 = 1
      "{\"name\":\"midday\",\"start\":\"10:00\",\"full_min\":30,\"poll_min\":0,\"partial_min\":5},"
      "{\"name\":\"evening\",\"start\":\"17:00\",\"full_min\":15,\"poll_min\":3,\"partial_min\":1}"
      "]}";
  CHECK(parseSchedule(j).valid == 0);
}

TEST_CASE("misaligned start (start_min %% full_min != 0) is rejected") {
  // 06:33 is 393 min; 393 % 15 = 3, so the morning tier's first Full would
  // never align to a tier-start minute. Reject.
  const char* j =
      "{\"version\":1,\"tiers\":["
      "{\"name\":\"night\",\"start\":\"22:00\",\"full_min\":15,\"poll_min\":0,\"partial_min\":0},"
      "{\"name\":\"morning\",\"start\":\"06:33\",\"full_min\":15,\"poll_min\":3,\"partial_min\":1},"
      "{\"name\":\"midday\",\"start\":\"10:00\",\"full_min\":30,\"poll_min\":0,\"partial_min\":5},"
      "{\"name\":\"evening\",\"start\":\"17:00\",\"full_min\":15,\"poll_min\":3,\"partial_min\":1}"
      "]}";
  CHECK(parseSchedule(j).valid == 0);
}

TEST_CASE("integer overflow on full_min is rejected before bounds-check") {
  const char* j =
      "{\"version\":1,\"tiers\":["
      "{\"name\":\"night\",\"start\":\"22:00\",\"full_min\":99999999,\"poll_min\":0,\"partial_min\":0},"
      "{\"name\":\"morning\",\"start\":\"06:30\",\"full_min\":15,\"poll_min\":3,\"partial_min\":1},"
      "{\"name\":\"midday\",\"start\":\"10:00\",\"full_min\":30,\"poll_min\":0,\"partial_min\":5},"
      "{\"name\":\"evening\",\"start\":\"17:00\",\"full_min\":15,\"poll_min\":3,\"partial_min\":1}"
      "]}";
  CHECK(parseSchedule(j).valid == 0);
}

TEST_CASE("negative integer is rejected") {
  const char* j =
      "{\"version\":1,\"tiers\":["
      "{\"name\":\"night\",\"start\":\"22:00\",\"full_min\":15,\"poll_min\":0,\"partial_min\":0},"
      "{\"name\":\"morning\",\"start\":\"06:30\",\"full_min\":-15,\"poll_min\":3,\"partial_min\":1},"
      "{\"name\":\"midday\",\"start\":\"10:00\",\"full_min\":30,\"poll_min\":0,\"partial_min\":5},"
      "{\"name\":\"evening\",\"start\":\"17:00\",\"full_min\":15,\"poll_min\":3,\"partial_min\":1}"
      "]}";
  CHECK(parseSchedule(j).valid == 0);
}

TEST_CASE("malformed HH:MM start is rejected") {
  const char* j =
      "{\"version\":1,\"tiers\":["
      "{\"name\":\"night\",\"start\":\"22:00\",\"full_min\":15,\"poll_min\":0,\"partial_min\":0},"
      "{\"name\":\"morning\",\"start\":\"6:30\",\"full_min\":15,\"poll_min\":3,\"partial_min\":1}," // missing leading 0
      "{\"name\":\"midday\",\"start\":\"10:00\",\"full_min\":30,\"poll_min\":0,\"partial_min\":5},"
      "{\"name\":\"evening\",\"start\":\"17:00\",\"full_min\":15,\"poll_min\":3,\"partial_min\":1}"
      "]}";
  CHECK(parseSchedule(j).valid == 0);
}

TEST_CASE("HH:MM hour > 23 is rejected") {
  const char* j =
      "{\"version\":1,\"tiers\":["
      "{\"name\":\"night\",\"start\":\"24:00\",\"full_min\":15,\"poll_min\":0,\"partial_min\":0},"
      "{\"name\":\"morning\",\"start\":\"06:30\",\"full_min\":15,\"poll_min\":3,\"partial_min\":1},"
      "{\"name\":\"midday\",\"start\":\"10:00\",\"full_min\":30,\"poll_min\":0,\"partial_min\":5},"
      "{\"name\":\"evening\",\"start\":\"17:00\",\"full_min\":15,\"poll_min\":3,\"partial_min\":1}"
      "]}";
  CHECK(parseSchedule(j).valid == 0);
}

TEST_CASE("fnv32: empty payload hashes to FNV offset basis") {
  // FNV-1a 32-bit offset basis (no bytes consumed) = 0x811c9dc5.
  CHECK(fw::wake::fnv32("") == 0x811c9dc5u);
}

TEST_CASE("fnv32: 'a' hashes to a known value") {
  // Standard test vector: FNV-1a 32-bit of "a" = 0xe40c292c.
  CHECK(fw::wake::fnv32("a") == 0xe40c292cu);
}

TEST_CASE("fnv32: matches HA-side validator output for the canonical payload") {
  // Cross-check with `python3 ha/scripts/validate_wake_schedule.py
  // ha/config/wake_schedule.yaml | python3 -c 'import sys; ...'`. If this
  // breaks, HA's expected-hash sensor and the device's published hash
  // will diverge and operators will see permanent mismatches.
  const char* canonical_json =
      "{\"version\":1,\"tiers\":["
      "{\"name\":\"morning\",\"start\":\"06:30\",\"full_min\":15,\"poll_min\":3,\"partial_min\":1},"
      "{\"name\":\"midday\",\"start\":\"10:00\",\"full_min\":30,\"poll_min\":0,\"partial_min\":5},"
      "{\"name\":\"evening\",\"start\":\"17:00\",\"full_min\":15,\"poll_min\":3,\"partial_min\":1},"
      "{\"name\":\"night\",\"start\":\"22:00\",\"full_min\":15,\"poll_min\":0,\"partial_min\":0}"
      "]}";
  CHECK(fw::wake::fnv32(canonical_json) == 0xf676e451u);
}

TEST_CASE("escape sequences in string fields are rejected") {
  // Names can't legitimately need escapes; reject so a payload with embedded
  // `\"` (which could complicate parsing) fails fast.
  const char* j =
      "{\"version\":1,\"tiers\":["
      "{\"name\":\"ni\\\"ght\",\"start\":\"22:00\",\"full_min\":15,\"poll_min\":0,\"partial_min\":0},"
      "{\"name\":\"morning\",\"start\":\"06:30\",\"full_min\":15,\"poll_min\":3,\"partial_min\":1},"
      "{\"name\":\"midday\",\"start\":\"10:00\",\"full_min\":30,\"poll_min\":0,\"partial_min\":5},"
      "{\"name\":\"evening\",\"start\":\"17:00\",\"full_min\":15,\"poll_min\":3,\"partial_min\":1}"
      "]}";
  CHECK(parseSchedule(j).valid == 0);
}
