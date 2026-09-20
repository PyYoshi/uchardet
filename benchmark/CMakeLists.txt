add_executable(uchardet-benchmark uchardet-benchmark.cpp)
target_link_libraries(uchardet-benchmark ${UCHARDET_LIBRARY})

add_executable(uchardet-output uchardet-output.cpp)
target_link_libraries(uchardet-output ${UCHARDET_LIBRARY})

add_executable(uchardet-conformance uchardet-conformance.cpp)
target_link_libraries(uchardet-conformance ${UCHARDET_LIBRARY})
