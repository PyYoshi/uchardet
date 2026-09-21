<!-- SPDX-License-Identifier: MIT -->
# 固定block試作のallocation API呼び出し

1024-byte候補を、静的リンク時に解決される8経路で観測する。
既存MITの`models/experimental/allocation-hooks.cpp`を再利用し、自己検証の成功後に
構築・初回文書・warm文書・破棄を分けて数える。時間計測とは併用しない。

対象: malloc/calloc/realloc/free、throwing・unalignedのscalar/array new/delete。
対象外: shared library内部、strdup内部、aligned/nothrow/sized/custom allocator、mmap。
counterはsingle-thread診断用。physical allocation数・要求byte数・live/peak memoryを
報告するtoolではない。freeが非zeroでmallocがzeroでも、確保がなかったとは解釈しない。

## 条件と結果（2026-09-22）

- 64-bit Linux、GCC16.2.1、C++11/Release、非LTOのstatic library。
- 固定tuningの16入力（cp1252/UTF-8各8）、各4096 bytes以下、process timeout10秒。
- 旧whole、直接1024-byte feed、adapter外部whole、adapter外部1-byteを比較。
- 初回後に16回処理し、次の1回のreset/feed/finalizeをwarm区間として観測。
- 入力I/Oとsnapshotの文字列構築は計測区間外。

全16入力で:

- adapterの構築は直接fixedに対し`new`が1回増加（1→2）。buffer確保と対応する。
- 初回文書とwarm文書の対象8 counterは直接fixedとadapterで一致。
- adapterの外部wholeと1-byteは、全counterと候補snapshotが一致。
- adapter破棄の`delete`は直接fixedより1回多い。
- 計測あり/なしで全方式の候補数・順序・encoding・language null区別・confidence bits・doneが一致。
- 直接fixedとadapterのsnapshotは、保存済み1024-byte canonical観測とも一致。
- 同じreportへの再実行は全byte一致。

例: 1708-byte cp1252文書ではwarm中malloc/newが0、freeが56だった。
候補のstrdupによる確保をこのhookは数えないため、「warm中allocationなし」とは主張しない。
初期構築+1回だけからmemory gateの10%条件を判断することもできない。

## 再現

```sh
cmake --build /tmp/uchardet-fixed-block-build --target \
  uchardet-fixed-block-allocations uchardet-fixed-block-allocations-plain
uv run --no-project python benchmark/fixed_block_allocations.py \
  /workspace/archives/v3-corpus/paris-training-tuning-generated-v1/manifest.json \
  /workspace/archives/v3-corpus/fixed-block-tuning-v3.json \
  /tmp/uchardet-fixed-block-build/benchmark/uchardet-fixed-block-allocations-plain \
  /tmp/uchardet-fixed-block-build/benchmark/uchardet-fixed-block-allocations \
  /workspace/archives/v3-corpus/fixed-block-allocations-v2.json
```

targetはLinux/64-bit/GCCまたはClang/static構成でのみ作成し、EXCLUDE_FROM_ALL、installなし。
`/workspace`は実際の保存先に置き換える。独立holdoutは未開封。
report content hash: `f1e073ce9e72d360435be5986af752c18e4f01d48b0edd29d1fc90ccceb22dad`。
binary・driver・入力hashと全counterを保存している。
追加3 tests成功、ローカルbenchmark suiteは41成功・5 skip。

初回/peak/live memory、エラー/OOM、追加fuzzの検証ではない。P01を再開しない。
既定API/model/engineは変更せず、標準採用は引き続き保留する。
