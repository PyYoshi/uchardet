#include <algorithm>
#include <chrono>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <iterator>
#include <string>
#include <vector>

#include "uchardet.h"

namespace {

volatile size_t result_checksum = 0;
size_t chunk_size = 0;

struct Input {
  std::string path;
  std::vector<char> bytes;
};

std::vector<Input> load_inputs(int argc, char** argv, int first_file) {
  std::vector<Input> inputs;
  for (int i = first_file; i < argc; ++i) {
    std::ifstream stream(argv[i], std::ios::binary);
    if (!stream) {
      std::cerr << "could not open " << argv[i] << '\n';
      std::exit(EXIT_FAILURE);
    }
    Input input;
    input.path = argv[i];
    input.bytes.assign(std::istreambuf_iterator<char>(stream),
                       std::istreambuf_iterator<char>());
    inputs.push_back(input);
  }
  return inputs;
}

void consume_result(uchardet_t detector) {
  const size_t candidates = uchardet_get_n_candidates(detector);
  result_checksum += candidates;
  if (candidates != 0) {
    const char* encoding = uchardet_get_encoding(detector, 0);
    result_checksum += static_cast<unsigned char>(encoding[0]);
  }
}

void feed(uchardet_t detector, const Input& input) {
  const char* data = input.bytes.empty() ? "" : &input.bytes[0];
  const size_t step = chunk_size == 0 ? input.bytes.size() : chunk_size;
  if (step == 0) {
    if (uchardet_handle_data(detector, data, 0) != 0) {
      std::cerr << "uchardet_handle_data failed for " << input.path << '\n';
      std::exit(EXIT_FAILURE);
    }
    return;
  }
  for (size_t offset = 0; offset < input.bytes.size(); offset += step) {
    const size_t length = std::min(step, input.bytes.size() - offset);
    if (uchardet_handle_data(detector, data + offset, length) != 0) {
      std::cerr << "uchardet_handle_data failed for " << input.path << '\n';
      std::exit(EXIT_FAILURE);
    }
  }
}

void run_fresh(const std::vector<Input>& inputs) {
  for (std::vector<Input>::const_iterator input = inputs.begin();
       input != inputs.end(); ++input) {
    uchardet_t detector = uchardet_new();
    if (!detector) {
      std::cerr << "uchardet_new failed\n";
      std::exit(EXIT_FAILURE);
    }
    feed(detector, *input);
    uchardet_data_end(detector);
    consume_result(detector);
    uchardet_delete(detector);
  }
}

void run_reuse(const std::vector<Input>& inputs) {
  uchardet_t detector = uchardet_new();
  if (!detector) {
    std::cerr << "uchardet_new failed\n";
    std::exit(EXIT_FAILURE);
  }
  for (std::vector<Input>::const_iterator input = inputs.begin();
       input != inputs.end(); ++input) {
    feed(detector, *input);
    uchardet_data_end(detector);
    consume_result(detector);
    uchardet_reset(detector);
  }
  uchardet_delete(detector);
}

}  // namespace

int main(int argc, char** argv) {
  if (argc < 5) {
    std::cerr << "usage: " << argv[0]
              << " fresh|reuse ITERATIONS CHUNK_SIZE FILE...\n";
    return EXIT_FAILURE;
  }
  const std::string mode(argv[1]);
  void (*run)(const std::vector<Input>&) = NULL;
  if (mode == "fresh") {
    run = run_fresh;
  } else if (mode == "reuse") {
    run = run_reuse;
  } else {
    std::cerr << "mode must be fresh or reuse\n";
    return EXIT_FAILURE;
  }
  const long iterations = std::strtol(argv[2], NULL, 10);
  if (iterations < 1) {
    std::cerr << "ITERATIONS must be positive\n";
    return EXIT_FAILURE;
  }
  const long parsed_chunk_size = std::strtol(argv[3], NULL, 10);
  if (parsed_chunk_size < 0) {
    std::cerr << "CHUNK_SIZE must be non-negative\n";
    return EXIT_FAILURE;
  }
  chunk_size = static_cast<size_t>(parsed_chunk_size);
  const std::vector<Input> inputs = load_inputs(argc, argv, 4);
  if (inputs.empty()) {
    std::cerr << "at least one input file is required\n";
    return EXIT_FAILURE;
  }

  for (int warmup = 0; warmup < 3; ++warmup) {
    run(inputs);
  }

  typedef std::chrono::steady_clock Clock;
  std::vector<double> samples;
  for (long iteration = 0; iteration < iterations; ++iteration) {
    const Clock::time_point start = Clock::now();
    run(inputs);
    const Clock::time_point end = Clock::now();
    samples.push_back(
        std::chrono::duration<double, std::milli>(end - start).count());
  }
  std::sort(samples.begin(), samples.end());
  const double median = samples[samples.size() / 2];
  std::cout << "mode,files,bytes,iterations,chunk_size,median_ms,checksum\n";
  size_t total_bytes = 0;
  for (std::vector<Input>::const_iterator input = inputs.begin();
       input != inputs.end(); ++input) {
    total_bytes += input->bytes.size();
  }
  std::cout << mode << ',' << inputs.size() << ',' << total_bytes << ','
            << iterations << ',' << chunk_size << ',' << median << ','
            << result_checksum << '\n';
  std::cout << "samples_ms";
  for (std::vector<double>::const_iterator sample = samples.begin();
       sample != samples.end(); ++sample) {
    std::cout << ',' << *sample;
  }
  std::cout << '\n';
  return EXIT_SUCCESS;
}
