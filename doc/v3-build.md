<!-- SPDX-License-Identifier: MIT -->
# v3 native 開発ビルド

新規の本書、`CMakePresets.json`、GitHub workflow は MIT。
ライセンス本文は `LICENSES/MIT.txt` を参照する。既存の engine・model の
ライセンスは変更しない。

## ローカル手順

CMake 3.21 以上、Ninja、GCC / Clang / AppleClang / MSVC を用意する。
Windows では x64 Native Tools Command Prompt から実行する。

```sh
cmake --preset release
cmake --build --preset release --parallel 2
ctest --preset release
```

`release` を `debug`、`sanitize`、`cxx20` に置き換えて比較できる。
`sanitize` は GCC / GNU-style Clang の ASan + UBSan で、MSVC は対象外。
Debug は sanitizer と独立しており、library version も変更しない。
既知の corpus 失敗の除外は維持し、個々の CTest は 30 秒で打ち切る。

各 preset は static library、native benchmark / output tool、test を生成する。
CLI は外部 getopt の有無による差を避けるため無効にしている。
通常の CMake configure は従来どおり shared library と CLI を既定で生成する。
`BUILD_TESTING=OFF` で test を除外できる。

必要に応じて `UCHARDET_WARNINGS`、`UCHARDET_ASAN`、`UCHARDET_UBSAN` を
個別に指定する。警告は既存コードの分析用であり、まだ error へ昇格しない。
sanitizer のオプションはこのディレクトリ配下の target にだけ適用する。

## CI と未完了の互換性ゲート

GitHub Actions は dev の PR / push を対象にし、Markdown / reStructuredText
のみの変更では起動しない。手動実行は可能。ジョブ上限は 15 分、同じ PR の
古い run はキャンセルする。GCC、Clang sanitizer、AppleClang、MSVC を検証する。

C++ の既定規格は 11 を維持し、`cxx20` は候補の互換性検証専用とする。
native CI の成功だけでは配布環境の C++20 対応を証明できない。
cChardet の Cython build、manylinux の libstdc++ / glibc、macOS deployment
target、Windows runtime、各 wheel architecture の検証が別途必要である。
MSVC CLI 用 getopt と Windows shared-library 実行はこの preset の検証範囲外。

GNU 系の既存 SSE / FP オプションは維持し、MSVC へ GNU オプションを渡さない。
候補結果の維持は conformance 比較で確認する。性能測定には `release` を使い、
sanitizer / Debug の値を公開性能と混ぜない。
