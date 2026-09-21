// SPDX-License-Identifier: MIT
// Selected static-link call sites, NOT a heap profiler or failure-injection test.
#include "fixed-block-detector.h"
#include "../models/experimental/allocation-hooks.hpp"
#include <cstdint>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <string>

static void begin_count() {
#ifdef UCHARDET_ALLOCATION_PROBE
  allocation_calls = {};
  allocation_tracking = true;
#endif
}
static AllocationCalls end_count() {
#ifdef UCHARDET_ALLOCATION_PROBE
  allocation_tracking = false;
  return allocation_calls;
#else
  return {};
#endif
}
static void print_calls(const AllocationCalls& c) {
  std::cout << "{\"malloc\":" << c.malloc_calls << ",\"calloc\":" << c.calloc_calls
            << ",\"realloc\":" << c.realloc_calls << ",\"free\":" << c.free_calls
            << ",\"new\":" << c.new_calls << ",\"new_array\":" << c.new_array_calls
            << ",\"delete\":" << c.delete_calls << ",\"delete_array\":" << c.delete_array_calls << '}';
}

// Hex strings make the complete ordered candidate snapshot JSON-safe without
// allocating anything inside a counted interval.
static std::string snapshot(uchardet_t handle) {
  std::ostringstream out;
  out << uchardet_is_done(handle) << ':' << uchardet_get_n_candidates(handle);
  for (size_t i = 0; i < uchardet_get_n_candidates(handle); ++i) {
    for (const char* value : {uchardet_get_encoding(handle, i), uchardet_get_language(handle, i)}) {
      out << (value ? ":present:" : ":null:");
      if (value) for (const unsigned char* p = reinterpret_cast<const unsigned char*>(value); *p; ++p)
        out << std::hex << std::setw(2) << std::setfill('0') << static_cast<unsigned>(*p);
    }
    const float confidence = uchardet_get_confidence(handle, i);
    uint32_t bits;
    static_assert(sizeof(bits) == sizeof(confidence), "binary32 required");
    std::memcpy(&bits, &confidence, sizeof(bits));
    out << ':' << std::hex << std::setw(8) << std::setfill('0') << bits;
  }
  return out.str();
}

class Direct {
 public:
  Direct(size_t block, size_t) : detector_(uchardet_new(), &uchardet_delete), block_(block) {
    if (!detector_) throw std::runtime_error("allocation failed");
  }
  void reset() { uchardet_reset(detector_.get()); }
  void feed(const char* data, size_t length) {
    for (size_t offset = 0; offset < length && !uchardet_is_done(detector_.get()); offset += block_)
      if (uchardet_handle_data(detector_.get(), data + offset, std::min(block_, length - offset)))
        throw std::runtime_error("feed failed");
  }
  void finish() { uchardet_data_end(detector_.get()); }
  uchardet_t handle() const { return detector_.get(); }
 private:
  std::unique_ptr<struct uchardet, decltype(&uchardet_delete)> detector_;
  size_t block_;
};

template<class Detector>
static void observe(const char* name, size_t block, size_t chunk, const std::vector<char>& bytes) {
  AllocationCalls construction, first, warm, destruction;
  std::string first_snapshot, warm_snapshot;
  const size_t step = chunk ? chunk : std::max(size_t(1), bytes.size());
  const auto process = [&](Detector& detector) {
    detector.reset();
    for (size_t offset = 0; offset < bytes.size(); offset += step)
      detector.feed(bytes.data() + offset, std::min(step, bytes.size() - offset));
    detector.finish();
  };
  begin_count();
  {
    Detector detector(block, 4096);
    construction = end_count();
    begin_count();
    process(detector);
    first = end_count();
    first_snapshot = snapshot(detector.handle());
    for (size_t i = 0; i < 16; ++i) process(detector);
    begin_count();
    process(detector);
    warm = end_count();
    warm_snapshot = snapshot(detector.handle());
    if (warm_snapshot != first_snapshot) throw std::runtime_error("reuse changed candidates");
    begin_count();
  }
  destruction = end_count();
  std::cout << '"' << name << "\":{\"construction\":";
  print_calls(construction);
  std::cout << ",\"first_document\":"; print_calls(first);
  std::cout << ",\"warm_document\":"; print_calls(warm);
  std::cout << ",\"destruction\":"; print_calls(destruction);
  std::cout << ",\"snapshot\":\"" << warm_snapshot << "\"}";
}

int main(int argc, char** argv) {
  try {
    if (argc != 2) throw std::invalid_argument("usage: fixed-block-allocations FILE");
#ifdef UCHARDET_ALLOCATION_PROBE
    allocation_self_test();
#endif
    std::ifstream input(argv[1], std::ios::binary);
    if (!input) throw std::runtime_error("cannot open input");
    std::vector<char> bytes(4097);
    input.read(bytes.data(), static_cast<std::streamsize>(bytes.size()));
    bytes.resize(static_cast<size_t>(input.gcount()));
    if (input.bad() || bytes.size() > 4096) throw std::runtime_error("input exceeds bounded pilot");
    std::cout << "{\"byte_length\":" << bytes.size() << ",\"block\":1024,\"modes\":{";
    observe<Direct>("whole", 4096, 0, bytes);
    std::cout << ',';
    observe<Direct>("direct_fixed", 1024, 0, bytes);
    std::cout << ',';
    observe<experimental::FixedBlockDetector>("adapter_whole", 1024, 0, bytes);
    std::cout << ',';
    observe<experimental::FixedBlockDetector>("adapter_byte", 1024, 1, bytes);
    std::cout << "}}\n";
    return 0;
  } catch (const std::exception& error) {
    end_count();
    std::cerr << error.what() << '\n';
    return 1;
  }
}
