#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include "doctest.h"

// Smoke test: the host build links and doctest runs.
TEST_CASE("hello, sim") {
  CHECK(1 + 1 == 2);
}
