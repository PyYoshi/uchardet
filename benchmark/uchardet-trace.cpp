// SPDX-License-Identifier: MIT
// Copyright (c) 2026 cChardet contributors
// Observes internal protected state without modifying the detector library.
#include "nscore.h"
#include "nsUniversalDetector.h"
#include "nsCharSetProber.h"
#include <algorithm>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <vector>

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

class Observer : public nsUniversalDetector {
public:
  Observer() : nsUniversalDetector(NS_FILTER_ALL), offset_(0) {}
  void Snapshot(const char* event, size_t offset) {
    offset_ = offset;
    std::cout << "{\"schema_version\":1,\"event\":"; quoted(event);
    std::cout << ",\"offset\":" << offset << ",\"input_state\":" << mInputState
              << ",\"start\":" << (mStart ? "true" : "false")
              << ",\"got_data\":" << (mGotData ? "true" : "false")
              << ",\"done\":" << (mDone ? "true" : "false")
              << ",\"shortcut_encoding\":"; quoted(shortcutCharset);
    std::cout << ",\"probers\":{";
    const char* names[] = {"multibyte_group", "singlebyte_group", "latin1"};
    for (size_t i = 0; i < NUM_OF_CHARSET_PROBERS; ++i) {
      if (i) std::cout << ',';
      quoted(names[i]); std::cout << ':'; State(mCharSetProbers[i]);
    }
    std::cout << ",\"escape\":"; State(mEscCharSetProber);
    std::cout << "}}\n";
  }
protected:
  void Report(const char* encoding, const char* language, float confidence) override {
    uint32_t bits; std::memcpy(&bits, &confidence, sizeof(bits));
    std::cout << "{\"schema_version\":1,\"event\":\"raw_report\",\"offset\":" << offset_
              << ",\"encoding\":"; quoted(encoding);
    std::cout << ",\"language\":"; quoted(language);
    std::cout << ",\"confidence_bits\":\"" << std::hex << std::setw(8) << std::setfill('0')
              << bits << std::dec << "\"}\n";
  }
private:
  static void State(nsCharSetProber* prober) {
    if (!prober) { std::cout << "null"; return; }
    switch (prober->GetState()) {
      case eDetecting: quoted("detecting"); break;
      case eFoundIt: quoted("found"); break;
      case eNotMe: quoted("rejected"); break;
      default: throw std::runtime_error("unknown prober state");
    }
  }
  size_t offset_;
};

int main(int argc, char** argv) {
  try {
    static_assert(sizeof(float) == sizeof(uint32_t) && std::numeric_limits<float>::is_iec559,
                  "exact output requires IEEE-754 binary32");
    if (argc != 3) throw std::runtime_error("usage: uchardet-trace 0|1|7|64|1024 FILE (maximum 64 KiB)");
    const std::string chunk(argv[1]);
    if (chunk != "0" && chunk != "1" && chunk != "7" && chunk != "64" && chunk != "1024")
      throw std::runtime_error("invalid chunk schedule");
    std::ifstream stream(argv[2], std::ios::binary);
    if (!stream) throw std::runtime_error("cannot open input");
    std::vector<char> bytes(65537);
    stream.read(bytes.data(), static_cast<std::streamsize>(bytes.size()));
    const size_t length = static_cast<size_t>(stream.gcount());
    if (stream.bad() || length > 65536) throw std::runtime_error("read failed or input exceeds 64 KiB diagnostic limit");
    bytes.resize(length);
    Observer detector;
    detector.Snapshot("initial", 0);
    const size_t step = chunk == "0" ? length : static_cast<size_t>(std::stoul(chunk));
    size_t offset = 0;
    do {
      const size_t count = std::min(step, length - offset);
      if (detector.HandleData(bytes.empty() ? "" : bytes.data() + offset, static_cast<PRUint32>(count)) != NS_OK)
        throw std::runtime_error("HandleData failed");
      offset += count;
      detector.Snapshot("after_feed", offset);
    } while (offset < length);
    detector.DataEnd();
    detector.Snapshot("after_end", offset);
    return 0;
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n'; return 1;
  }
}
