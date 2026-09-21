<!-- SPDX-License-Identifier: MIT -->
# 固定 block 入力 adapter の非デフォルト試作

2026-09-22、maintainerの再開指示を受け、第3試作として着手。
既存のBOM/model generator試作は保存する。P01は再開しない。
この実験用classを公開C API、Python API、既定engineへ採用する変更ではない。

## 実験契約

- block長とevidence上限は明示指定。初期pilotはいずれも最大4096 bytes。
- 同じ入力prefixを、外部feedの境界に関係なく固定blockでcoreへ渡す。
- evidence上限0は空prefix。上限に達してもEOF扱いにしない。
- 空feedではflushしない。finishで端数を一度だけflushし、native finalizeを一度呼ぶ。
- nativeがdoneなら追加入力を処理しない。doneの初回観測はcoreへ渡したbyte位置で記録する。
  finishだけでdoneになる場合とfeed中にdoneになる場合を混同しない。
- resetでpending buffer、counter、終了状態とnative文書状態を初期化する。
- finishはadapterとしてべき等。finish後feedはlogic_error。native API自体の保証は変更しない。
- adapterの保持bufferはblock長分のみ。入力全体をadapterに保存しない。
  これはnative内部のmemory上限やallocation失敗時の保証を意味しない。

## 初期検証

`test-fixed-block.cpp`は通常の空/ASCII/UTF-8/cp1252/BOM入力とblock前後長を使用する。
外部chunkは1/7/64/1024/4096 bytes、内部blockは1/7/64/1024 bytes、
evidence上限は0/1/7/64/4096 bytes。
別のfresh C API detectorへ同じprefixを固定blockで渡した結果をoracleとする。
候補数・順序・encoding・languageのnull区別・confidence bits・done、
処理byte数・core feed回数・最初のdone位置を比較する。
途中reset、空feed、繰返しfinish、finish後feed拒否も確認する。

```sh
cmake -S . -B /tmp/uchardet-fixed-block-build -DBUILD_BENCHMARK=ON -DBUILD_SHARED_LIBS=OFF
cmake --build /tmp/uchardet-fixed-block-build --target uchardet-fixed-block-test
timeout 10s /tmp/uchardet-fixed-block-build/benchmark/uchardet-fixed-block-test
```

targetはEXCLUDE_FROM_ALLでinstall対象外。既存libraryを変更しない。
旧whole-inputの候補と一致することは要求しない。corpusの品質・性能・memory評価、
block長の選定、Python/wheel統合、標準採用は未実施。
独立holdoutやP01対象の大入力/追加fuzzは扱わない。

## 固定tuning pilot（2026-09-22）

`fixed_block_compare.py`は保存済みratio chunk reportのcontent hashを固定し、
同じmanifestのcomplete tuning 16入力だけを読み、各入力のhashを照合する。
legacy whole-inputが保存観測と完全一致することを先に確認する。
各processに10秒のtimeoutを設け、入力は4096 bytes以下に限定する。
block候補は事前に1/7/64/1024、外部chunkはwhole/1/7/64/1024と固定した。
生成modelは使わず、既存の標準modelを同じlibraryから呼び出す。

初回結果: 16入力×4 block×5 chunkの320観測で、外部chunk間の候補・最終done・
core feed回数・処理byte数・coreの最初のdone位置が一致した。
callerのfeed回数やdoneを返す外部境界は一致要件に含めない。

| 内部block | cp1252 exact / 8 | cp1252 decode-equivalent / 8 | UTF-8 exact / 8 |
| --- | --- | --- | --- |
| 1 | 0 | 0 | 8 |
| 7 | 2 | 6 | 8 |
| 64 | 4 | 8 | 8 |
| 1024 | 4 | 8 | 8 |

legacy whole-inputはcp1252 exact 4/8、decode-equivalent 8/8。
whole-inputと候補が完全一致しない入力はblock 1/7/64で各16/16、1024で4/16。
64/1024のtop-1品質が同じでもconfidenceや下位候補の同等性を意味しない。
このtuning結果からblock長を標準採用しない。独立holdoutは未開封。

```sh
uv run --no-project python benchmark/fixed_block_compare.py \
  /workspace/archives/v3-corpus/paris-training-tuning-generated-v1/manifest.json \
  /workspace/archives/v3-corpus/paris24-ratio-chunks-v1.json \
  /tmp/uchardet-fixed-block-build/benchmark/uchardet-fixed-block \
  /tmp/uchardet-fixed-block-build/benchmark/uchardet-conformance \
  /workspace/archives/v3-corpus/fixed-block-tuning-v1.json
```

`/workspace`は保存済みprivate artifactの実際の配置へ置き換える。
reportはbinary hash・driver hash・入力hash・全観測を含み、同じ出力への上書きは
内容が同一の場合のみ許可する。性能・memory測定や一般化した精度保証ではない。
