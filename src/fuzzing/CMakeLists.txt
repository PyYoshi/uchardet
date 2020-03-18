# for macOS: $ cmake -DCMAKE_CXX_COMPILER="`brew --prefix llvm`/bin/clang++" ../

set(
	UCHARDET_SOURCES
	uchardet_fuzzer.cpp
)

add_definitions(
	-O0
	-g3
	-fsanitize=fuzzer,address
)
set(CMAKE_CXX_FLAGS "-fsanitize=fuzzer,address")
set(CMAKE_C_FLAGS "-fsanitize=fuzzer,address")
set(CMAKE_EXE_LINKER_FLAGS "-fsanitize=fuzzer,address")
set(CMAKE_MODULE_LINKER_FLAGS "-fsanitize=fuzzer,address")
set(CMAKE_SHARED_LINKER_FLAGS "-fsanitize=fuzzer,address")

set(FUZZER_BINARY uchardet_fuzzer)

add_executable(
	${FUZZER_BINARY}
	${UCHARDET_SOURCES}
)

target_link_libraries(
	${FUZZER_BINARY}
	${UCHARDET_LIBRARY}
)

# install(
# 	TARGETS
# 		${FUZZER_BINARY}
# 	RUNTIME DESTINATION
# 		${CMAKE_INSTALL_BINDIR}
# )
