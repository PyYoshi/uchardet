add_executable(uchardet-benchmark uchardet-benchmark.cpp)
target_link_libraries(uchardet-benchmark ${UCHARDET_LIBRARY})

add_executable(uchardet-output uchardet-output.cpp)
target_link_libraries(uchardet-output ${UCHARDET_LIBRARY})

add_executable(uchardet-conformance uchardet-conformance.cpp)
target_link_libraries(uchardet-conformance ${UCHARDET_LIBRARY})

# Explicit-only pilot; never installed or part of the default build.
add_executable(uchardet-fixed-block-test EXCLUDE_FROM_ALL test-fixed-block.cpp)
target_link_libraries(uchardet-fixed-block-test ${UCHARDET_LIBRARY})
add_executable(uchardet-fixed-block EXCLUDE_FROM_ALL uchardet-conformance.cpp)
target_compile_definitions(uchardet-fixed-block PRIVATE
  UCHARDET_FIXED_BLOCK_PILOT=1 UCHARDET_EXPERIMENTAL_INPUT_LIMIT=4096)
target_link_libraries(uchardet-fixed-block ${UCHARDET_LIBRARY})
add_executable(uchardet-fixed-block-timing EXCLUDE_FROM_ALL fixed-block-timing.cpp)
target_link_libraries(uchardet-fixed-block-timing ${UCHARDET_LIBRARY})

if(CMAKE_SYSTEM_NAME STREQUAL "Linux" AND CMAKE_SIZEOF_VOID_P EQUAL 8
   AND NOT BUILD_SHARED_LIBS AND CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
  add_executable(uchardet-fixed-block-allocations-plain EXCLUDE_FROM_ALL fixed-block-allocations.cpp)
  target_link_libraries(uchardet-fixed-block-allocations-plain ${UCHARDET_LIBRARY})
  add_executable(uchardet-fixed-block-allocations EXCLUDE_FROM_ALL
    fixed-block-allocations.cpp ../models/experimental/allocation-hooks.cpp)
  target_compile_definitions(uchardet-fixed-block-allocations PRIVATE UCHARDET_ALLOCATION_PROBE=1)
  target_compile_options(uchardet-fixed-block-allocations PRIVATE -fno-lto)
  target_link_libraries(uchardet-fixed-block-allocations ${UCHARDET_LIBRARY})
  foreach(symbol malloc calloc realloc free _Znwm _Znam _ZdlPv _ZdaPv)
    target_link_options(uchardet-fixed-block-allocations PRIVATE "-Wl,--wrap=${symbol}")
  endforeach()
endif()

if(TARGET libuchardet_experimental)
  add_executable(uchardet-conformance-experimental EXCLUDE_FROM_ALL uchardet-conformance.cpp)
  target_compile_definitions(uchardet-conformance-experimental PRIVATE UCHARDET_EXPERIMENTAL_INPUT_LIMIT=4096)
  target_link_libraries(uchardet-conformance-experimental libuchardet_experimental)
endif()

option(BUILD_INTROSPECTION "Build internal diagnostic observer (static builds only)" OFF)
if(BUILD_INTROSPECTION)
  if(BUILD_SHARED_LIBS)
    message(FATAL_ERROR "BUILD_INTROSPECTION requires BUILD_SHARED_LIBS=OFF")
  endif()
  add_executable(uchardet-trace uchardet-trace.cpp)
  target_link_libraries(uchardet-trace ${UCHARDET_LIBRARY})
  add_executable(uchardet-filter-profile uchardet-filter-profile.cpp)
  target_link_libraries(uchardet-filter-profile ${UCHARDET_LIBRARY})
endif()
