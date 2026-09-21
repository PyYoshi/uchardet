// SPDX-License-Identifier: MIT
#include "fixed-block-detector.h"
#include <cstdint>
#include <iostream>
#include <sstream>
#include <string>

static void require(bool ok, const char* message) {
  if (!ok) throw std::runtime_error(message);
}

static std::string snapshot(uchardet_t detector) {
  std::ostringstream out;
  out << uchardet_is_done(detector) << ':' << uchardet_get_n_candidates(detector);
  for (size_t i = 0; i < uchardet_get_n_candidates(detector); ++i) {
    const char* language = uchardet_get_language(detector, i);
    const float confidence = uchardet_get_confidence(detector, i);
    uint32_t bits;
    static_assert(sizeof(bits) == sizeof(confidence), "binary32 required");
    std::memcpy(&bits, &confidence, sizeof(bits));
    out << '|' << uchardet_get_encoding(detector, i) << ':'
        << (language ? "present:" : "null:") << (language ? language : "") << ':' << bits;
  }
  return out.str();
}

int main() {
  try {
    const std::vector<std::string> inputs = {
      "", "a", "plain ASCII text", "caf\xc3\xa9 et th\xc3\xa9",
      "caf\xe9 et th\xe9", std::string(135, 'a'),
      std::string(63, 'a'), std::string(64, 'a'), std::string(65, 'a'),
      "\xef\xbb\xbf" "UTF-8 text"
    };
    size_t comparisons = 0;
    for (size_t block : {size_t(1), size_t(7), size_t(64), size_t(1024)}) {
      for (size_t limit : {size_t(0), size_t(1), size_t(7), size_t(64), size_t(4096)}) {
        experimental::FixedBlockDetector reused(block, limit);
        for (const auto& input : inputs) {
          // Direct C API oracle, fed the canonical prefix in fixed blocks.
          std::unique_ptr<struct uchardet, decltype(&uchardet_delete)>
              direct(uchardet_new(), &uchardet_delete);
          require(bool(direct), "allocation failed");
          const size_t length = std::min(input.size(), limit);
          size_t processed = 0, calls = 0, first_done = 0;
          bool observed = false;
          while (processed < length && !uchardet_is_done(direct.get())) {
            const size_t step = std::min(block, length - processed);
            require(!uchardet_handle_data(direct.get(), input.data() + processed, step), "feed failed");
            processed += step;
            ++calls;
            if (uchardet_is_done(direct.get())) { observed = true; first_done = processed; }
          }
          uchardet_data_end(direct.get());
          const std::string expected = snapshot(direct.get());
          for (size_t chunk : {size_t(1), size_t(7), size_t(64), size_t(1024), size_t(4096)}) {
            reused.reset();
            reused.feed("discarded", 9);
            reused.reset();
            for (size_t offset = 0; offset < input.size(); offset += chunk) {
              reused.feed(input.data() + offset, std::min(chunk, input.size() - offset));
              const size_t pending = reused.pending();
              reused.feed("", 0);
              require(reused.pending() == pending, "empty feed flushed evidence");
            }
            reused.finish();
            require(snapshot(reused.handle()) == expected, "candidate/done mismatch");
            require(reused.processed() == processed && reused.calls() == calls,
                    "canonical feed counters differ");
            require(reused.observed_done() == observed && reused.first_done() == first_done,
                    "core completion offset differs");
            reused.finish();
            require(snapshot(reused.handle()) == expected, "finish is not idempotent");
            bool rejected = false;
            try { reused.feed("x", 1); }
            catch (const std::logic_error&) { rejected = true; }
            require(rejected, "feed after finish was not rejected");
            ++comparisons;
          }
        }
      }
    }
    for (size_t block : {size_t(0), size_t(4097)}) {
      bool rejected = false;
      try { experimental::FixedBlockDetector invalid(block, 4096); }
      catch (const std::invalid_argument&) { rejected = true; }
      require(rejected, "invalid block accepted");
    }
    std::cout << "fixed-block comparisons: " << comparisons << '\n';
    return 0;
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
}
