// SPDX-License-Identifier: MIT
// Independent observation harness. Detector/filter implementations stay in the library.
#include "sequence-model.hpp"
#include <algorithm>
#include <chrono>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>
#ifdef __linux__
#include <sys/resource.h>
#endif
#ifdef UCHARDET_ALLOCATION_PROBE
#include "allocation-hooks.hpp"
#endif

class SequenceProbe : public nsSingleByteCharSetProber {
 public:
  explicit SequenceProbe(const SequenceModel* model) : nsSingleByteCharSetProber(model) {}

  void print() {
    const float confidence = GetConfidence(0);
    std::uint32_t bits = 0;
    static_assert(sizeof(bits) == sizeof(confidence), "binary32 required");
    std::memcpy(&bits, &confidence, sizeof(bits));
    std::cout << "{\"state\":" << static_cast<int>(GetState())
              << ",\"total_characters\":" << mTotalChar
              << ",\"control_characters\":" << mCtrlChar
              << ",\"frequent_characters\":" << mFreqChar
              << ",\"out_characters\":" << mOutChar
              << ",\"total_sequences\":" << mTotalSeqs
              << ",\"last_order\":" << static_cast<unsigned>(mLastOrder)
              << ",\"categories\":[";
    for (unsigned i = 0; i < NUMBER_OF_SEQ_CAT; ++i) {
      if (i) std::cout << ',';
      std::cout << mSeqCounters[i];
    }
    // A bit string remains JSON-valid even if a model produces nonfinite confidence.
    std::cout << "],\"confidence_bits\":\"" << std::hex << std::setw(8)
              << std::setfill('0') << bits << std::dec << "\"}";
  }
};

int main(int argc, char** argv) {
  try {
    if (argc != 2 && argc != 3)
      throw std::runtime_error("usage: sequence-probe FILE [ITERATIONS]");
#ifdef UCHARDET_ALLOCATION_PROBE
    if (argc != 2) throw std::runtime_error("allocation and timing are separate modes");
    allocation_self_test();
#endif
    std::uint64_t iterations = 0;
    if (argc == 3) {
      const std::string argument(argv[2]);
      if (argument.empty() || argument.find_first_not_of("0123456789") != std::string::npos)
        throw std::runtime_error("iterations must be unsigned decimal");
      iterations = std::stoull(argument);
      if (iterations == 0 || iterations > 1000000)
        throw std::runtime_error("iterations must be in [1, 1000000]");
    }
    std::ifstream input(argv[1], std::ios::binary);
    if (!input) throw std::runtime_error("cannot open input");
    const std::size_t limit = 65536;
    std::vector<char> data(limit + 1);
    input.read(data.data(), static_cast<std::streamsize>(data.size()));
    if (input.bad()) throw std::runtime_error("input read failed");
    data.resize(static_cast<std::size_t>(input.gcount()));
    if (data.size() > limit) throw std::runtime_error("input exceeds 65536 byte diagnostic limit");
    std::vector<char> buffer(std::max<std::size_t>(1, data.size()));
    PRUint32 retained = 0;
    SequenceProbe probe(&uchardet_sequence_pilot::model);
    const auto run = [&]() {
      probe.Reset();
      retained = 0;
      if (!data.empty()) {
        nsCharSetProber::FilterWithoutEnglishLettersToBuffer(
            data.data(), static_cast<PRUint32>(data.size()), buffer.data(), retained);
      }
      if (retained > data.size()) throw std::runtime_error("unexpected filter length");
      // Match the SBCS group's empty-filter behavior; a single non-reversed prober.
      if (retained) probe.HandleData(buffer.data(), retained, nullptr, nullptr);
      const float confidence = probe.GetConfidence(0);
      std::uint32_t bits = 0;
      std::memcpy(&bits, &confidence, sizeof(bits));
      return bits;
    };
    run();
#ifdef UCHARDET_ALLOCATION_PROBE
    for (unsigned i = 0; i < 128; ++i) run();
    allocation_tracking = true;
    run();
    allocation_tracking = false;
#endif
    std::int64_t elapsed_ns = 0;
    volatile std::uint64_t checksum = 0;
    const unsigned warmup = 128;
#ifdef __linux__
    struct rusage usage_before = {}, usage_after = {};
#endif
    if (iterations) {
      for (unsigned i = 0; i < warmup; ++i) checksum += run();
      checksum = 0;
#ifdef __linux__
      if (getrusage(RUSAGE_SELF, &usage_before) != 0)
        throw std::runtime_error("cannot read resource usage before timing");
#endif
      const auto start = std::chrono::steady_clock::now();
      for (std::uint64_t i = 0; i < iterations; ++i) checksum += run();
      elapsed_ns = std::chrono::duration_cast<std::chrono::nanoseconds>(
          std::chrono::steady_clock::now() - start).count();
#ifdef __linux__
      if (getrusage(RUSAGE_SELF, &usage_after) != 0)
        throw std::runtime_error("cannot read resource usage after timing");
#endif
    }
    std::cout << "{\"schema\":\"sequence-native-probe-v1\",\"raw_bytes\":" << data.size()
              << ",\"filtered_bytes\":" << retained
              << ",\"model_encoding\":\"" << probe.GetCharSetName(0)
              << "\",\"model_language\":\"" << probe.GetLanguage(0)
              << "\",\"model_frequent_count\":" << uchardet_sequence_pilot::model.freqCharCount
              << ",\"snapshot\":";
    probe.print();
#ifdef UCHARDET_ALLOCATION_PROBE
    const AllocationCalls& c = allocation_calls;
    std::cout << ",\"allocation_calls\":{\"malloc\":" << c.malloc_calls
              << ",\"calloc\":" << c.calloc_calls << ",\"realloc\":" << c.realloc_calls
              << ",\"free\":" << c.free_calls << ",\"new\":" << c.new_calls
              << ",\"new_array\":" << c.new_array_calls
              << ",\"delete\":" << c.delete_calls
              << ",\"delete_array\":" << c.delete_array_calls << '}';
#endif
    std::cout << ",\"after_reset\":";
    probe.Reset();
    probe.print();
    if (iterations) {
      std::cout << ",\"benchmark\":{\"iterations\":" << iterations
                << ",\"warmup_iterations\":" << warmup
                << ",\"elapsed_ns\":" << elapsed_ns
                << ",\"checksum\":" << checksum << ",\"resources\":";
#ifdef __linux__
      const auto cpu_ns = [](const struct timeval& value) -> std::int64_t {
        return static_cast<std::int64_t>(value.tv_sec) * 1000000000 +
               static_cast<std::int64_t>(value.tv_usec) * 1000;
      };
      std::cout << "{\"user_cpu_ns\":" << cpu_ns(usage_after.ru_utime) - cpu_ns(usage_before.ru_utime)
                << ",\"system_cpu_ns\":" << cpu_ns(usage_after.ru_stime) - cpu_ns(usage_before.ru_stime)
                << ",\"voluntary_switches\":" << usage_after.ru_nvcsw - usage_before.ru_nvcsw
                << ",\"involuntary_switches\":" << usage_after.ru_nivcsw - usage_before.ru_nivcsw
                << ",\"minor_faults\":" << usage_after.ru_minflt - usage_before.ru_minflt
                << ",\"major_faults\":" << usage_after.ru_majflt - usage_before.ru_majflt << '}';
#else
      std::cout << "null";
#endif
      std::cout << '}';
    }
    std::cout << "}\n";
    return std::cout ? 0 : 1;
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
}
