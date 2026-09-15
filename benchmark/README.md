# Native benchmark

The benchmark calls the public uchardet C API directly and loads every input
before timing, so filesystem and language-binding overhead are excluded.

Build an optimized static library and the benchmark tools:

```sh
cmake -S . -B build-benchmark \
  -DCMAKE_BUILD_TYPE=Release \
  -DBUILD_SHARED_LIBS=OFF \
  -DBUILD_BINARY=OFF \
  -DBUILD_BENCHMARK=ON
cmake --build build-benchmark --parallel
```

Measure fresh detectors with whole-file input or 64-byte chunks. The output
contains the median and every sorted sample in milliseconds.

```sh
build-benchmark/benchmark/uchardet-benchmark fresh 100 0 test/[a-z][a-z]/*
build-benchmark/benchmark/uchardet-benchmark fresh 100 64 test/[a-z][a-z]/*
```

Use `reuse` instead of `fresh` to reset one detector between files. The
`uchardet-output` tool emits every candidate, language, and confidence and is
intended for exact output comparisons between builds:

```sh
build-benchmark/benchmark/uchardet-output 0 test/[a-z][a-z]/*
```
