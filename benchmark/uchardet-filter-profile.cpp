// SPDX-License-Identifier: MIT
// Observe the existing filter; do not copy or replace its implementation.
#include "nsCharSetProber.h"
#include <algorithm>
#include <array>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <map>
#include <stdexcept>
#include <string>
#include <vector>

struct Statistics {
  std::array<std::uint64_t, 256> symbols{};
  std::map<unsigned, std::uint64_t> pairs;
  std::uint64_t bytes = 0;
  unsigned previous = 0;

  void append(const char* data, std::size_t length) {
    for (std::size_t i = 0; i < length; ++i) {
      const unsigned value = static_cast<unsigned char>(data[i]);
      if (bytes != 0) ++pairs[previous * 256 + value];
      ++symbols[value];
      ++bytes;
      previous = value;
    }
  }

  void print() const {
    std::cout << "{\"bytes\":" << bytes << ",\"symbols\":[";
    for (std::size_t i = 0; i < symbols.size(); ++i) {
      if (i) std::cout << ',';
      std::cout << symbols[i];
    }
    std::cout << "],\"pairs\":[";
    bool first = true;
    for (const auto& item : pairs) {
      if (!first) std::cout << ',';
      first = false;
      std::cout << '[' << item.first / 256 << ',' << item.first % 256
                << ',' << item.second << ']';
    }
    std::cout << "]}";
  }
};

int main(int argc, char** argv) {
  try {
    if (argc != 3) throw std::runtime_error("usage: uchardet-filter-profile CHUNK_SIZE FILE");
    const std::string argument(argv[1]);
    if (argument.empty() || argument.find_first_not_of("0123456789") != std::string::npos)
      throw std::runtime_error("chunk must be an unsigned decimal integer");
    const auto chunk = std::stoull(argument);
    const std::size_t limit = 65536;
    if (chunk > limit) throw std::runtime_error("chunk exceeds diagnostic limit");
    std::ifstream input(argv[2], std::ios::binary);
    if (!input) throw std::runtime_error("cannot open input");
    std::vector<char> data(limit + 1);
    input.read(data.data(), static_cast<std::streamsize>(data.size()));
    if (input.bad()) throw std::runtime_error("input read failed");
    data.resize(static_cast<std::size_t>(input.gcount()));
    if (data.size() > limit) throw std::runtime_error("input exceeds 65536 byte diagnostic limit");
    Statistics raw, filtered;
    raw.append(data.data(), data.size());
    std::vector<char> scratch(std::max<std::size_t>(1, data.size()));
    std::vector<std::pair<std::size_t, PRUint32>> calls;
    const std::size_t step = chunk ? static_cast<std::size_t>(chunk) : data.size();
    for (std::size_t offset = 0; offset < data.size();) {
      const auto length = std::min(step, data.size() - offset);
      PRUint32 output_length = 0;
      nsCharSetProber::FilterWithoutEnglishLettersToBuffer(
          data.data() + offset, static_cast<PRUint32>(length), scratch.data(), output_length);
      if (output_length > length) throw std::runtime_error("unexpected filter length");
      filtered.append(scratch.data(), output_length);
      calls.emplace_back(length, output_length);
      offset += length;
    }
    std::cout << "{\"schema\":\"sbcs-filter-profile-v1\",\"chunk_size\":" << chunk
              << ",\"raw\":";
    raw.print();
    std::cout << ",\"filtered\":";
    filtered.print();
    std::cout << ",\"calls\":[";
    for (std::size_t i = 0; i < calls.size(); ++i) {
      if (i) std::cout << ',';
      std::cout << '[' << calls[i].first << ',' << calls[i].second << ']';
    }
    std::cout << "]}\n";
    return std::cout ? 0 : 1;
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
}
