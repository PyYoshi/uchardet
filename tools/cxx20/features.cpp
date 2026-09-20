// SPDX-License-Identifier: MIT
// Toolchain availability probe only. Never linked into the detector or installed.
#include <algorithm>
#include <array>
#include <bit>
#include <concepts>
#include <cstdint>
#include <iostream>
#include <memory>
#include <ranges>
#include <span>
#include <utility>
#include <vector>
#include <version>

static_assert(__cplusplus >= 202002L);
static_assert(__cpp_lib_span >= 202002L);
static_assert(__cpp_lib_bit_cast >= 201806L);
static_assert(__cpp_lib_concepts >= 202002L);
static_assert(__cpp_lib_ranges >= 201911L);
static_assert(__cpp_lib_integer_comparison_functions >= 202002L);
static_assert(std::integral<std::uint32_t>);
static_assert(!std::in_range<unsigned>(-1));
static_assert(std::cmp_less(-1, 0u));

int main()
{
    auto owner = std::make_unique<std::array<int, 4>>();
    *owner = {4, 1, 3, 2};
    const std::span<int> view(*owner);
    std::ranges::sort(view);
    if (view.front() != 1 || view.back() != 4 || view.subspan(1, 2)[1] != 3)
        return 1;
    int sum = 0;
    for (int value : view | std::views::filter([](int n) { return n % 2 == 0; }))
        sum += value;
    if (sum != 6)
        return 2;
    const std::uint32_t value = 0x12345678u;
    const auto bytes = std::bit_cast<std::array<unsigned char, sizeof(value)>>(value);
    if (std::bit_cast<std::uint32_t>(bytes) != value)
        return 3;
    std::vector<int> values(view.begin(), view.end());
    if (std::erase_if(values, [](int n) { return n % 2 == 0; }) != 2 ||
        values != std::vector<int>({1, 3}))
        return 4;
    std::cout << "{\"schema_version\":1,\"cplusplus\":" << __cplusplus
              << ",\"span\":" << __cpp_lib_span
              << ",\"bit_cast\":" << __cpp_lib_bit_cast
              << ",\"concepts\":" << __cpp_lib_concepts
              << ",\"ranges\":" << __cpp_lib_ranges
              << ",\"integer_comparison\":" << __cpp_lib_integer_comparison_functions;
#if defined(_LIBCPP_VERSION)
    std::cout << ",\"stdlib\":\"libc++\",\"stdlib_version\":" << _LIBCPP_VERSION;
#elif defined(__GLIBCXX__)
    std::cout << ",\"stdlib\":\"libstdc++\",\"stdlib_version\":" << __GLIBCXX__;
#elif defined(_MSVC_STL_VERSION)
    std::cout << ",\"stdlib\":\"msvc-stl\",\"stdlib_version\":" << _MSVC_STL_VERSION;
#else
    std::cout << ",\"stdlib\":\"unknown\"";
#endif
    std::cout << ",\"status\":\"passed\"}\n";
}
