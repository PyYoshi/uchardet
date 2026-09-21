// SPDX-License-Identifier: MIT
// Small valid-input lifecycle checks, not arbitrary-byte or allocation-failure tests.
#include "uchardet.h"
#include <cstdint>
#include <cstring>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

class Detector {
 public:
  Detector() : handle_(uchardet_new()) {
    if (!handle_) throw std::runtime_error("detector allocation failed");
  }
  ~Detector() { uchardet_delete(handle_); }
  Detector(const Detector&) = delete;
  Detector& operator=(const Detector&) = delete;
  uchardet_t get() const { return handle_; }
 private:
  uchardet_t handle_;
};

struct Candidate {
  std::string encoding, language;
  bool language_present;
  std::uint32_t confidence;
  bool operator==(const Candidate& other) const {
    return encoding == other.encoding && language == other.language &&
           language_present == other.language_present && confidence == other.confidence;
  }
};

struct Snapshot {
  bool done;
  std::vector<Candidate> candidates;
  bool operator==(const Snapshot& other) const {
    return done == other.done && candidates == other.candidates;
  }
};

static Snapshot snapshot(const Detector& detector) {
  Snapshot value;
  value.done = uchardet_is_done(detector.get()) != 0;
  const size_t count = uchardet_get_n_candidates(detector.get());
  for (size_t i = 0; i < count; ++i) {
    Candidate candidate;
    const char* encoding = uchardet_get_encoding(detector.get(), i);
    const char* language = uchardet_get_language(detector.get(), i);
    if (!encoding) throw std::runtime_error("candidate encoding is null");
    candidate.encoding = encoding;
    candidate.language_present = language != nullptr;
    candidate.language = language ? language : "";
    const float confidence = uchardet_get_confidence(detector.get(), i);
    static_assert(sizeof(confidence) == sizeof(candidate.confidence), "binary32 required");
    std::memcpy(&candidate.confidence, &confidence, sizeof(confidence));
    value.candidates.push_back(candidate);
  }
  return value;
}

static void require_equal(const Snapshot& actual, const Snapshot& expected, const char* stage) {
  if (!(actual == expected)) throw std::runtime_error(stage);
}

static void feed(const Detector& detector, const std::string& data) {
  if (uchardet_handle_data(detector.get(), data.data(), data.size()) != 0)
    throw std::runtime_error("normal input failed");
}

int main() {
  try {
    const std::vector<std::string> inputs = {
      "", "plain ASCII text", "caf\xc3\xa9 et th\xc3\xa9", "caf\xe9 et th\xe9"
    };
    Detector reused;
    Detector pristine;
    const Snapshot initial = snapshot(pristine);
    unsigned comparisons = 0;
    for (unsigned cycle = 0; cycle < 3; ++cycle) {
      for (const std::string& input : inputs) {
        uchardet_reset(reused.get());
        require_equal(snapshot(reused), initial, "reset differs from fresh detector");
        // Reset must discard a previous, unfinished document as well.
        feed(reused, "old ASCII document");
        uchardet_reset(reused.get());
        require_equal(snapshot(reused), initial, "reset after feed differs from fresh detector");
        Detector fresh;
        feed(reused, input);
        feed(fresh, input);
        require_equal(snapshot(reused), snapshot(fresh), "same-feed state differs after reset");
        uchardet_data_end(reused.get());
        uchardet_data_end(fresh.get());
        const Snapshot expected = snapshot(fresh);
        require_equal(snapshot(reused), expected, "final candidates differ after reset");
        require_equal(snapshot(reused), expected, "candidate getters changed finalized output");
        ++comparisons;
      }
    }
    std::cout << "fresh/reuse lifecycle comparisons: " << comparisons << '\n';
    return 0;
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
}
