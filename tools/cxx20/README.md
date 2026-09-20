<!-- SPDX-License-Identifier: MIT -->
# C++20 標準ライブラリ機能の独立 probe

`cxx20` preset だけで有効になる、小さな compile/run 検証です。
detector へリンクせず、install 対象にも含めません。通常 preset と既定規格は維持します。

```sh
cmake --preset cxx20
cmake --build --preset cxx20 --target uchardet-cxx20-probe
ctest --preset cxx20 -R '^cxx20-library-features$' -V
```

`BUILD_CXX20_PROBE=ON` で単独有効化も可能です。この target だけは必ず C++20、
言語拡張なしで構築します。probe の存在を理由に他 target の規格を変更しません。

検証対象:

- `std::span`: RAII 所有者の生存期間内の非所有 view / subspan
- concepts: `std::integral`
- `std::ranges::sort` と filter view
- `std::bit_cast`: 同サイズの byte 配列との往復（endian を仮定しない）
- `std::cmp_less` / `std::in_range`: signed / unsigned の比較・表現範囲
- `std::erase_if`: vector の条件付き削除

Release でも消えない戻り値検査を使います。feature-test macro と標準ライブラリの
識別情報を JSON で出力し、CTest の詳細出力で compiler matrix の記録を残します。
CI の `cxx20` 行で GNU / AppleClang / MSVC を検証します。

これは機能利用可能性の最小確認です。span の寿命や境界が自動的に安全になるわけではなく、
detector のメモリ安全性、標準ライブラリ全機能、最低 OS / CRT、manylinux wheel の
互換性は証明しません。新たな機能を本体へ採用するときは対象 artifact / runtime で
別途検証し、P01 の安全性調査を再開した結果とは扱いません。
