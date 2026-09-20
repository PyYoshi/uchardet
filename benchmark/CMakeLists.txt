add_executable(uchardet-benchmark uchardet-benchmark.cpp)
target_link_libraries(uchardet-benchmark ${UCHARDET_LIBRARY})

add_executable(uchardet-output uchardet-output.cpp)
target_link_libraries(uchardet-output ${UCHARDET_LIBRARY})

add_executable(uchardet-conformance uchardet-conformance.cpp)
target_link_libraries(uchardet-conformance ${UCHARDET_LIBRARY})

option(BUILD_INTROSPECTION "Build internal diagnostic observer (static builds only)" OFF)
if(BUILD_INTROSPECTION)
  if(BUILD_SHARED_LIBS)
    message(FATAL_ERROR "BUILD_INTROSPECTION requires BUILD_SHARED_LIBS=OFF")
  endif()
  add_executable(uchardet-trace uchardet-trace.cpp)
  target_link_libraries(uchardet-trace ${UCHARDET_LIBRARY})
endif()
