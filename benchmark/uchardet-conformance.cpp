// SPDX-License-Identifier: MIT
// Copyright (c) 2026 cChardet contributors
#include "uchardet.h"
#include <algorithm>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <iterator>
#include <limits>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>
#ifdef UCHARDET_FIXED_BLOCK_PILOT
#include "fixed-block-detector.h"
#endif

static void quoted(const char* value) {
  if (!value) { std::cout << "null"; return; }
  std::cout << '"';
  for (const unsigned char* p = reinterpret_cast<const unsigned char*>(value); *p; ++p) {
    if (*p == '"' || *p == '\\') std::cout << '\\' << *p;
    else if (*p < 32 || *p >= 127)
      std::cout << "\\u00" << std::hex << std::setw(2) << std::setfill('0')
                << static_cast<unsigned>(*p) << std::dec;
    else std::cout << *p;
  }
  std::cout << '"';
}

int main(int argc, char** argv) {
  try {
#ifdef UCHARDET_FIXED_BLOCK_PILOT
    if (argc < 6) throw std::runtime_error("usage: uchardet-fixed-block BLOCK LIMIT fresh|reuse CHUNK FILE...");
    const auto parameter = [](const char* text) -> size_t {
      const std::string value(text);
      if (value.empty() || value.find_first_not_of("0123456789") != std::string::npos)
        throw std::runtime_error("invalid block/limit parameter");
      const unsigned long number = std::stoul(value);
      if (number > 4096) throw std::runtime_error("pilot parameter exceeds 4096");
      return static_cast<size_t>(number);
    };
    const size_t block_size = parameter(argv[1]), evidence_limit = parameter(argv[2]);
    argc -= 2;
    argv += 2;
#endif
    if (argc < 4) throw std::runtime_error("usage: uchardet-conformance fresh|reuse 0|1|7|64|1024|random FILE...");
    const std::string mode(argv[1]), chunk(argv[2]);
    if (mode != "fresh" && mode != "reuse") throw std::runtime_error("invalid lifecycle mode");
    if (chunk != "0" && chunk != "1" && chunk != "7" && chunk != "64" && chunk != "1024" && chunk != "random")
      throw std::runtime_error("invalid chunk schedule");
    static_assert(sizeof(float) == sizeof(uint32_t) && std::numeric_limits<float>::is_iec559,
                  "exact output requires IEEE-754 binary32");
#ifdef UCHARDET_FIXED_BLOCK_PILOT
    std::unique_ptr<experimental::FixedBlockDetector> adapter;
#else
    typedef std::unique_ptr<struct uchardet, decltype(&uchardet_delete)> Detector;
    Detector detector(nullptr, &uchardet_delete);
#endif
    for (int file = 3; file < argc; ++file) {
      std::ifstream stream(argv[file], std::ios::binary);
      if (!stream) throw std::runtime_error("cannot open input");
#ifdef UCHARDET_EXPERIMENTAL_INPUT_LIMIT
      std::vector<char> bytes(UCHARDET_EXPERIMENTAL_INPUT_LIMIT + 1);
      stream.read(bytes.data(), static_cast<std::streamsize>(bytes.size()));
      bytes.resize(static_cast<size_t>(stream.gcount()));
      if (bytes.size() > UCHARDET_EXPERIMENTAL_INPUT_LIMIT)
        throw std::runtime_error("experimental input exceeds 4096 bytes");
#else
      const std::vector<char> bytes((std::istreambuf_iterator<char>(stream)), std::istreambuf_iterator<char>());
#endif
      if (stream.bad()) throw std::runtime_error("cannot read input");
#ifdef UCHARDET_FIXED_BLOCK_PILOT
      if (!adapter || mode == "fresh")
        adapter.reset(new experimental::FixedBlockDetector(block_size, evidence_limit));
      else adapter->reset();
      const uchardet_t handle = adapter->handle();
#else
      if (!detector || mode == "fresh") detector.reset(uchardet_new());
      else uchardet_reset(detector.get());
      if (!detector) throw std::runtime_error("detector allocation failed");
      const uchardet_t handle = detector.get();
#endif
      const bool initial_done = uchardet_is_done(handle) != 0;
      size_t offset = 0, calls = 0, first_done = 0;
      bool observed_done = false;
      uint32_t seed = 0x12345678;
      do {
        seed ^= seed << 13; seed ^= seed >> 17; seed ^= seed << 5;
        const size_t step = chunk == "random" ? 1 + seed % 1024 :
                            chunk == "0" ? bytes.size() : static_cast<size_t>(std::stoul(chunk));
        const size_t length = std::min(step, bytes.size() - offset);
#ifdef UCHARDET_FIXED_BLOCK_PILOT
        adapter->feed(bytes.empty() ? "" : &bytes[offset], length);
#else
        if (uchardet_handle_data(handle, bytes.empty() ? "" : &bytes[offset], length))
          throw std::runtime_error("handle_data failed");
#endif
        offset += length; ++calls;
        if (!observed_done && uchardet_is_done(handle)) { observed_done = true; first_done = offset; }
      } while (offset < bytes.size());
#ifdef UCHARDET_FIXED_BLOCK_PILOT
      adapter->finish();
#else
      uchardet_data_end(handle);
#endif
      std::cout << "{\"schema_version\":1,\"input_index\":" << file - 3
                << ",\"byte_length\":" << bytes.size() << ",\"initial_done\":" << (initial_done ? "true" : "false")
                << ",\"feed_calls\":" << calls << ",\"first_done_offset\":";
      if (observed_done) std::cout << first_done; else std::cout << "null";
#ifdef UCHARDET_FIXED_BLOCK_PILOT
      std::cout << ",\"block_size\":" << block_size << ",\"evidence_limit\":" << evidence_limit
                << ",\"core_processed_bytes\":" << adapter->processed()
                << ",\"core_feed_calls\":" << adapter->calls()
                << ",\"core_first_done_offset\":";
      if (adapter->observed_done()) std::cout << adapter->first_done(); else std::cout << "null";
#endif
      const size_t count = uchardet_get_n_candidates(handle);
      std::cout << ",\"final_done\":" << (uchardet_is_done(handle) ? "true" : "false")
                << ",\"candidate_count\":" << count << ",\"candidates\":[";
      for (size_t i = 0; i < count; ++i) {
        if (i) std::cout << ',';
        std::cout << "{\"encoding\":"; quoted(uchardet_get_encoding(handle, i));
        std::cout << ",\"language\":"; quoted(uchardet_get_language(handle, i));
        const float confidence = uchardet_get_confidence(handle, i);
        uint32_t bits; std::memcpy(&bits, &confidence, sizeof(bits));
        std::cout << ",\"confidence_bits\":\"" << std::hex << std::setw(8) << std::setfill('0') << bits << std::dec << "\"}";
      }
      std::cout << "]}\n";
    }
    return 0;
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n'; return 1;
  }
}
