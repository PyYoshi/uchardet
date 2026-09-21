// SPDX-License-Identifier: MIT
// Small warmed reuse timing; no filesystem I/O or detector creation in timed region.
#include "fixed-block-detector.h"
#include <chrono>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <string>

static size_t number(const char* text, size_t maximum) {
  const std::string value(text);
  if (value.empty() || value.find_first_not_of("0123456789") != std::string::npos)
    throw std::invalid_argument("invalid numeric parameter");
  const unsigned long parsed = std::stoul(value);
  if (parsed > maximum) throw std::invalid_argument("parameter exceeds pilot bound");
  return parsed;
}

int main(int argc, char** argv) {
  try {
    if (argc != 6) throw std::invalid_argument("usage: fixed-block-timing BLOCK EXTERNAL_CHUNK ITERATIONS REPEATS FILE");
    const size_t block = number(argv[1], 4096), chunk = number(argv[2], 4096);
    const size_t iterations = number(argv[3], 10000), repeats = number(argv[4], 31);
    if (!block || !iterations || !repeats) throw std::invalid_argument("zero parameter");
    std::ifstream input(argv[5], std::ios::binary);
    if (!input) throw std::runtime_error("cannot open input");
    std::vector<char> bytes(4097);
    input.read(bytes.data(), static_cast<std::streamsize>(bytes.size()));
    bytes.resize(static_cast<size_t>(input.gcount()));
    if (input.bad() || bytes.size() > 4096) throw std::runtime_error("input exceeds bounded pilot");
    const size_t external = chunk ? chunk : std::max(size_t(1), bytes.size());
    experimental::FixedBlockDetector adapter(block, 4096);
    typedef std::unique_ptr<struct uchardet, decltype(&uchardet_delete)> Detector;
    Detector whole(uchardet_new(), &uchardet_delete), fixed(uchardet_new(), &uchardet_delete);
    if (!whole || !fixed) throw std::runtime_error("allocation failed");
    const auto run = [&](size_t mode) -> size_t {
      uchardet_t handle;
      if (mode == 2) {
        adapter.reset();
        for (size_t offset = 0; offset < bytes.size(); offset += external)
          adapter.feed(bytes.data() + offset, std::min(external, bytes.size() - offset));
        adapter.finish();
        handle = adapter.handle();
      } else {
        handle = mode == 0 ? whole.get() : fixed.get();
        uchardet_reset(handle);
        const size_t step = mode == 0 ? std::max(size_t(1), bytes.size()) : block;
        for (size_t offset = 0; offset < bytes.size() && !uchardet_is_done(handle); offset += step)
          if (uchardet_handle_data(handle, bytes.data() + offset,
                                   std::min(step, bytes.size() - offset)))
            throw std::runtime_error("feed failed");
        uchardet_data_end(handle);
      }
      // Match the established benchmark's small result consumption, not Python conversion.
      const size_t count = uchardet_get_n_candidates(handle);
      return count + (count ? static_cast<unsigned char>(uchardet_get_encoding(handle, 0)[0]) : 0);
    };
    size_t expected[3];
    for (size_t mode = 0; mode < 3; ++mode) {
      expected[mode] = run(mode);
      for (size_t warm = 0; warm < 16; ++warm)
        if (run(mode) != expected[mode]) throw std::runtime_error("unstable warmup result");
    }
    std::vector<double> timings[3];
    std::vector<size_t> checksums[3];
    for (size_t trial = 0; trial < repeats; ++trial) {
      for (size_t order = 0; order < 3; ++order) {
        const size_t mode = (trial + order) % 3;
        size_t checksum = 0;
        const auto start = std::chrono::steady_clock::now();
        for (size_t iteration = 0; iteration < iterations; ++iteration) checksum += run(mode);
        const auto end = std::chrono::steady_clock::now();
        if (checksum != expected[mode] * iterations) throw std::runtime_error("timed checksum differs");
        timings[mode].push_back(std::chrono::duration<double, std::nano>(end - start).count() / iterations);
        checksums[mode].push_back(checksum);
      }
    }
    const char* names[] = {"whole", "direct_fixed", "adapter"};
    std::cout << std::setprecision(17) << "{\"byte_length\":" << bytes.size()
              << ",\"block\":" << block << ",\"external_chunk\":" << chunk
              << ",\"iterations\":" << iterations << ",\"repeats\":" << repeats
              << ",\"modes\":{";
    for (size_t mode = 0; mode < 3; ++mode) {
      if (mode) std::cout << ',';
      std::cout << '"' << names[mode] << "\":{\"trial_mean_ns\":[";
      for (size_t i = 0; i < repeats; ++i) {
        if (i) std::cout << ',';
        std::cout << timings[mode][i];
      }
      std::cout << "],\"checksums\":[";
      for (size_t i = 0; i < repeats; ++i) {
        if (i) std::cout << ',';
        std::cout << checksums[mode][i];
      }
      std::cout << "]}";
    }
    std::cout << "}}\n";
    return 0;
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
}
