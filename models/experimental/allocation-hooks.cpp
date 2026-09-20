// SPDX-License-Identifier: MIT
#include "allocation-hooks.hpp"
#include <cstddef>
#include <cstdlib>
#include <new>
#include <stdexcept>

bool allocation_tracking = false;
AllocationCalls allocation_calls = {};

extern "C" {
void* __real_malloc(std::size_t);
void* __real_calloc(std::size_t, std::size_t);
void* __real_realloc(void*, std::size_t);
void __real_free(void*);
void* __real__Znwm(std::size_t);
void* __real__Znam(std::size_t);
void __real__ZdlPv(void*);
void __real__ZdaPv(void*);

void* __wrap_malloc(std::size_t n) {
  if (allocation_tracking) ++allocation_calls.malloc_calls;
  return __real_malloc(n);
}
void* __wrap_calloc(std::size_t n, std::size_t size) {
  if (allocation_tracking) ++allocation_calls.calloc_calls;
  return __real_calloc(n, size);
}
void* __wrap_realloc(void* p, std::size_t n) {
  if (allocation_tracking) ++allocation_calls.realloc_calls;
  return __real_realloc(p, n);
}
void __wrap_free(void* p) {
  if (allocation_tracking) ++allocation_calls.free_calls;
  __real_free(p);
}
void* __wrap__Znwm(std::size_t n) {
  if (allocation_tracking) ++allocation_calls.new_calls;
  return __real__Znwm(n);
}
void* __wrap__Znam(std::size_t n) {
  if (allocation_tracking) ++allocation_calls.new_array_calls;
  return __real__Znam(n);
}
void __wrap__ZdlPv(void* p) {
  if (allocation_tracking) ++allocation_calls.delete_calls;
  __real__ZdlPv(p);
}
void __wrap__ZdaPv(void* p) {
  if (allocation_tracking) ++allocation_calls.delete_array_calls;
  __real__ZdaPv(p);
}
}

void allocation_self_test() {
  // Volatile function pointers prevent optimizing away calibration calls.
  void* (*volatile allocate)(std::size_t) = &std::malloc;
  void* (*volatile zero_allocate)(std::size_t, std::size_t) = &std::calloc;
  void* (*volatile resize)(void*, std::size_t) = &std::realloc;
  void (*volatile release)(void*) = &std::free;
  void* (*volatile cpp_allocate)(std::size_t) = &::operator new;
  void* (*volatile array_allocate)(std::size_t) = &::operator new[];
  void (*volatile cpp_release)(void*) = &::operator delete;
  void (*volatile array_release)(void*) = &::operator delete[];
  allocation_calls = {};
  allocation_tracking = true;
  void* p = allocate(16);
  void* q = zero_allocate(1, 16);
  void* resized = resize(p, 32);
  release(resized ? resized : p);
  release(q);
  cpp_release(cpp_allocate(16));
  array_release(array_allocate(16));
  allocation_tracking = false;
  const AllocationCalls& c = allocation_calls;
  if (c.malloc_calls != 1 || c.calloc_calls != 1 || c.realloc_calls != 1 ||
      c.free_calls != 2 || c.new_calls != 1 || c.new_array_calls != 1 ||
      c.delete_calls != 1 || c.delete_array_calls != 1)
    throw std::runtime_error("allocation call-site calibration failed");
  allocation_calls = {};
}
