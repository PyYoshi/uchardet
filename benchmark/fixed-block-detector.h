// SPDX-License-Identifier: MIT
// Non-default experiment; not an installed or supported public API.
#ifndef UCHARDET_EXPERIMENTAL_FIXED_BLOCK_DETECTOR_H
#define UCHARDET_EXPERIMENTAL_FIXED_BLOCK_DETECTOR_H

#include "uchardet.h"
#include <algorithm>
#include <cstring>
#include <memory>
#include <stdexcept>
#include <vector>

namespace experimental {
class FixedBlockDetector {
 public:
  // Both bounds are explicit experiment parameters, never library defaults.
  FixedBlockDetector(size_t block_size, size_t evidence_limit)
      : detector_(uchardet_new(), &uchardet_delete), block_(checked(block_size)),
        limit_(evidence_limit) {
    if (!detector_) throw std::runtime_error("detector allocation failed");
    if (limit_ > 4096) throw std::invalid_argument("pilot evidence exceeds 4096 bytes");
  }

  void feed(const char* data, size_t length) {
    if (closed_) throw std::logic_error("feed after finish requires reset");
    // Empty feed is not EOF and does not flush pending evidence.
    if (!length || done()) return;
    length = std::min(length, limit_ - accepted_);
    while (length && !done()) {
      const size_t take = std::min(length, block_.size() - pending_);
      std::memcpy(block_.data() + pending_, data, take);
      data += take;
      pending_ += take;
      accepted_ += take;
      length -= take;
      if (pending_ == block_.size()) flush();
    }
  }

  void finish() {
    if (closed_) return;
    if (pending_ && !done()) flush();
    uchardet_data_end(detector_.get());
    closed_ = true;
  }

  void reset() {
    uchardet_reset(detector_.get());
    pending_ = accepted_ = processed_ = calls_ = first_done_ = 0;
    observed_done_ = closed_ = false;
  }

  uchardet_t handle() const { return detector_.get(); }
  bool done() const { return uchardet_is_done(detector_.get()) != 0; }
  size_t processed() const { return processed_; }
  size_t calls() const { return calls_; }
  size_t pending() const { return pending_; }
  bool observed_done() const { return observed_done_; }
  size_t first_done() const { return first_done_; }

 private:
  static size_t checked(size_t size) {
    if (!size || size > 4096) throw std::invalid_argument("block must be 1..4096 bytes");
    return size;
  }
  void flush() {
    if (uchardet_handle_data(detector_.get(), block_.data(), pending_))
      throw std::runtime_error("handle_data failed");
    processed_ += pending_;
    pending_ = 0;
    ++calls_;
    if (!observed_done_ && done()) {
      observed_done_ = true;
      first_done_ = processed_;
    }
  }
  std::unique_ptr<struct uchardet, decltype(&uchardet_delete)> detector_;
  std::vector<char> block_;
  size_t limit_;
  size_t pending_ = 0, accepted_ = 0, processed_ = 0, calls_ = 0, first_done_ = 0;
  bool observed_done_ = false, closed_ = false;
};
}  // namespace experimental
#endif
