// SPDX-License-Identifier: MIT
// Linux/Itanium ABI, static-link call-site instrumentation; not a heap profiler.
#pragma once
#include <cstdint>

struct AllocationCalls {
  std::uint64_t malloc_calls, calloc_calls, realloc_calls, free_calls;
  std::uint64_t new_calls, new_array_calls, delete_calls, delete_array_calls;
};
extern bool allocation_tracking;
extern AllocationCalls allocation_calls;
void allocation_self_test();
