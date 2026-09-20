// SPDX-License-Identifier: MIT
// Independent observation harness. Detector/filter implementations stay in the library.
#include "sequence-model.hpp"
#include <algorithm>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <vector>

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
    if (argc != 2) throw std::runtime_error("usage: sequence-probe FILE");
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
    if (!data.empty()) {
      nsCharSetProber::FilterWithoutEnglishLettersToBuffer(
          data.data(), static_cast<PRUint32>(data.size()), buffer.data(), retained);
    }
    if (retained > data.size()) throw std::runtime_error("unexpected filter length");
    SequenceProbe probe(&uchardet_sequence_pilot::model);
    // Match the SBCS group's empty-filter behavior. This is a single, non-reversed prober.
    if (retained) probe.HandleData(buffer.data(), retained, nullptr, nullptr);
    std::cout << "{\"schema\":\"sequence-native-probe-v1\",\"raw_bytes\":" << data.size()
              << ",\"filtered_bytes\":" << retained
              << ",\"model_encoding\":\"" << probe.GetCharSetName(0)
              << "\",\"model_language\":\"" << probe.GetLanguage(0)
              << "\",\"model_frequent_count\":" << uchardet_sequence_pilot::model.freqCharCount
              << ",\"snapshot\":";
    probe.print();
    std::cout << ",\"after_reset\":";
    probe.Reset();
    probe.print();
    std::cout << "}\n";
    return std::cout ? 0 : 1;
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
}
