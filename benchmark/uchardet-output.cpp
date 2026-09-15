#include <algorithm>
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <iterator>
#include <string>
#include <vector>

#include "uchardet.h"

int main(int argc, char** argv) {
  if (argc < 3) {
    std::cerr << "usage: " << argv[0] << " CHUNK_SIZE FILE...\n";
    return 1;
  }
  const long parsed_chunk_size = std::strtol(argv[1], NULL, 10);
  if (parsed_chunk_size < 0) {
    std::cerr << "CHUNK_SIZE must be non-negative\n";
    return 1;
  }
  const size_t chunk_size = static_cast<size_t>(parsed_chunk_size);
  for (int i = 2; i < argc; ++i) {
    std::ifstream stream(argv[i], std::ios::binary);
    if (!stream) {
      std::cerr << "could not open " << argv[i] << '\n';
      return 1;
    }
    const std::vector<char> bytes((std::istreambuf_iterator<char>(stream)),
                                  std::istreambuf_iterator<char>());
    uchardet_t detector = uchardet_new();
    const char* data = bytes.empty() ? "" : &bytes[0];
    if (!detector) {
      std::cerr << "detection failed for " << argv[i] << '\n';
      return 1;
    }
    const size_t step = chunk_size == 0 ? bytes.size() : chunk_size;
    if (step == 0) {
      if (uchardet_handle_data(detector, data, 0) != 0) {
        std::cerr << "detection failed for " << argv[i] << '\n';
        return 1;
      }
    } else {
      for (size_t offset = 0; offset < bytes.size(); offset += step) {
        const size_t length = std::min(step, bytes.size() - offset);
        if (uchardet_handle_data(detector, data + offset, length) != 0) {
          std::cerr << "detection failed for " << argv[i] << '\n';
          return 1;
        }
      }
    }
    uchardet_data_end(detector);
    const size_t candidates = uchardet_get_n_candidates(detector);
    std::cout << argv[i] << '\t' << candidates;
    for (size_t candidate = 0; candidate < candidates; ++candidate) {
      const char* encoding = uchardet_get_encoding(detector, candidate);
      const char* language = uchardet_get_language(detector, candidate);
      std::cout << '\t' << (encoding ? encoding : "<null>")
                << '\t' << (language ? language : "<null>")
                << '\t' << std::setprecision(9)
                << uchardet_get_confidence(detector, candidate);
    }
    std::cout << '\n';
    uchardet_delete(detector);
  }
  return 0;
}
