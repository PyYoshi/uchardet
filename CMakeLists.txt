######## Project settings
cmake_minimum_required(VERSION 3.21)
include(CheckCCompilerFlag)
set (PACKAGE_NAME uchardet)
project (${PACKAGE_NAME} CXX C)
include(CTest)

######## Package information
set (PACKAGE_URL https://www.freedesktop.org/wiki/Software/uchardet/)
set (PACKAGE_BUGREPORT https://gitlab.freedesktop.org/uchardet/uchardet/-/issues)
set (UCHARDET_VERSION_MAJOR 0)
set (UCHARDET_VERSION_MINOR 0)
set (UCHARDET_VERSION_REVISION 8)

set (
	UCHARDET_VERSION
	${UCHARDET_VERSION_MAJOR}.${UCHARDET_VERSION_MINOR}.${UCHARDET_VERSION_REVISION}
)
if (NOT DEFINED CMAKE_CXX_STANDARD)
    set(CMAKE_CXX_STANDARD 11)
endif ()
set(CMAKE_CXX_STANDARD_REQUIRED ON)

######## Directory

include(GNUInstallDirs)

######## Configuration

option(BUILD_BINARY "Build the CLI tool." ON)
option(BUILD_BENCHMARK "Build the native benchmark tool." OFF)
option(BUILD_CXX20_PROBE "Build standalone C++20 library feature probe (not linked to detector)." OFF)
option(UCHARDET_WARNINGS "Enable additional compiler warnings (not errors)." OFF)
option(UCHARDET_ASAN "Instrument this build with AddressSanitizer." OFF)
option(UCHARDET_UBSAN "Instrument this build with UndefinedBehaviorSanitizer." OFF)
if (UCHARDET_WARNINGS)
    if (MSVC)
        add_compile_options(/W4)
    else ()
        add_compile_options(-Wall -Wextra -Wpedantic)
    endif ()
endif ()
if (UCHARDET_ASAN OR UCHARDET_UBSAN)
    if (NOT CMAKE_CXX_COMPILER_ID MATCHES "^(GNU|Clang|AppleClang)$" OR MSVC)
        message(FATAL_ERROR "Sanitizer presets require GCC or Clang with GNU-style flags")
    endif ()
    add_compile_options(-fno-omit-frame-pointer)
    if (UCHARDET_ASAN)
        add_compile_options(-fsanitize=address)
        add_link_options(-fsanitize=address)
    endif ()
    if (UCHARDET_UBSAN)
        add_compile_options(-fsanitize=undefined -fno-sanitize-recover=undefined)
        add_link_options(-fsanitize=undefined)
    endif ()
endif ()
option(BUILD_SHARED_LIBS "Build shared library and link executable to it." ON)
option(CHECK_SSE2 "Check and enable SSE2 extensions if supported. Disabling SSE on platforms which support it may decrease performances." ON)
set(TARGET_ARCHITECTURE "" CACHE STRING "Target CPU architecture. It is autodetected if not specified.")

if (BUILD_SHARED_LIBS)
	option(BUILD_STATIC "Build static library" ON)
endif (BUILD_SHARED_LIBS)

if (TARGET_ARCHITECTURE STREQUAL "")
    string(TOLOWER "${CMAKE_SYSTEM_PROCESSOR}" TARGET_ARCHITECTURE)
endif (TARGET_ARCHITECTURE STREQUAL "")

if (NOT MSVC AND TARGET_ARCHITECTURE MATCHES ".*(x86|amd|i686).*")
    CHECK_C_COMPILER_FLAG(-msse2 SUPPORTS_CFLAG_SSE2)
    CHECK_C_COMPILER_FLAG(-mfpmath=sse SUPPORTS_CFLAG_SSE_MATH)
    if (CHECK_SSE2 AND SUPPORTS_CFLAG_SSE2 AND SUPPORTS_CFLAG_SSE_MATH)
        set(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -msse2 -mfpmath=sse")
        set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -msse2 -mfpmath=sse")
    else (CHECK_SSE2 AND SUPPORTS_CFLAG_SSE2 AND SUPPORTS_CFLAG_SSE_MATH)
        set(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -ffloat-store")
        set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -ffloat-store")
    endif (CHECK_SSE2 AND SUPPORTS_CFLAG_SSE2 AND SUPPORTS_CFLAG_SSE_MATH)
endif ()

configure_file(
	uchardet.pc.in
	uchardet.pc
	@ONLY
)

install(
	FILES
		${CMAKE_CURRENT_BINARY_DIR}/uchardet.pc
	DESTINATION
		${CMAKE_INSTALL_LIBDIR}/pkgconfig
)

######## Subdirectories

add_subdirectory(src)
add_subdirectory(doc)
if (BUILD_TESTING)
    add_subdirectory(test)
endif ()
if (BUILD_BENCHMARK)
    add_subdirectory(benchmark)
endif ()
if (BUILD_CXX20_PROBE)
    add_subdirectory(tools/cxx20)
endif ()

######## Exported targets

install(
	EXPORT UchardetTargets
	FILE ${PACKAGE_NAME}-targets.cmake
	NAMESPACE ${PACKAGE_NAME}::
	DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/${PACKAGE_NAME}
)

export(
	EXPORT UchardetTargets
	FILE "${CMAKE_CURRENT_BINARY_DIR}/${PACKAGE_NAME}-targets.cmake"
	NAMESPACE ${PACKAGE_NAME}::
)

include(CMakePackageConfigHelpers)
write_basic_package_version_file(
	${PACKAGE_NAME}-config-version.cmake
	VERSION ${UCHARDET_VERSION}
	COMPATIBILITY AnyNewerVersion
)

configure_file(
	${PACKAGE_NAME}-config.cmake.in
	${PACKAGE_NAME}-config.cmake
	@ONLY
)

install (
	FILES
		"${CMAKE_CURRENT_BINARY_DIR}/${PACKAGE_NAME}-config.cmake"
		"${CMAKE_CURRENT_BINARY_DIR}/${PACKAGE_NAME}-config-version.cmake"
	DESTINATION
		${CMAKE_INSTALL_LIBDIR}/cmake/${PACKAGE_NAME}
)
