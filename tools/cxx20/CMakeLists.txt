# SPDX-License-Identifier: MIT
add_executable(uchardet-cxx20-probe features.cpp)
set_target_properties(uchardet-cxx20-probe PROPERTIES
    CXX_STANDARD 20 CXX_STANDARD_REQUIRED YES CXX_EXTENSIONS NO)
if(MSVC)
    target_compile_options(uchardet-cxx20-probe PRIVATE /Zc:__cplusplus /EHsc /W4)
else()
    target_compile_options(uchardet-cxx20-probe PRIVATE -Wall -Wextra -Wpedantic)
endif()
if(BUILD_TESTING)
    add_test(NAME cxx20-library-features COMMAND uchardet-cxx20-probe)
    set_tests_properties(cxx20-library-features PROPERTIES TIMEOUT 10)
endif()
