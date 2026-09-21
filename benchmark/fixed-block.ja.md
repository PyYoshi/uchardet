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
  /workspace/archives/v3-corpus/fixed-block-tuning-v3.json
```

`/workspace`は保存済みprivate artifactの実際の配置へ置き換える。
reportはbinary hash・driver hash・入力hash・全観測を含み、同じ出力への上書きは
内容が同一の場合のみ許可する。性能・memory測定や一般化した精度保証ではない。

最終driverで再実行したreportのcontent hash:
`d198e153f5167a561d5809f011717def074fb3ab3991d84fa0f438bad816c63d`。
driver hash: `ff20a322644fabf6778dcea38ab44145ff06bb00ed765e339c1aee92e36efc67`。
adapter binary: `b3f82885dcc9dab19b08dd30e26add6daf3a9b83599c62cea5eb8faf03a473fb`、
baseline binary: `2944d943c50af9a76222617e9591bb6294526b5e18d6390b978501187d67501e`。
再実行のreport全byte一致。v1/v2はdriverのmetadata検証・記録拡充前の保存物であり、
結果の選別ではない。各blockの観測結果は同じだった。

追加の7 unittestは、固定report改変、用途/境界/encoding/hash metadata、重複ID、
範囲外pathの拒否、CLI引数・入力上限、fresh/resetとevidence上限を検証する。
ローカルのbenchmark suiteは36件中31成功・5 skip（各追加toolの環境指定条件）。
初回PR CIは11件成功。追加testを含む最終headのCIは別途確認する。

## 既存validationでの固定block比較（2026-09-22）

`--split validation`を明示すると、保存済みfull-engine reportのhash
`7b4695e8ff78effdeca177f71cf761081b46c64427ae8ad5c1d58de02e7e7265`と
対応manifestへ固定する。tuningとvalidationは同じ入力として扱わない。
独立holdoutの指定は受け付けない。結果を見たblock追加やモデル変更は行っていない。

Paris validation 16録音のcp1252/UTF-8各16入力（計32）のすべてを評価した。
32×4内部block×5外部chunkの640観測で、同じblock長の候補/done/core位置が一致した。
再実行のreport全byte一致。

| 内部block | cp1252 exact / 16 | cp1252 decode-equivalent / 16 | UTF-8 exact / 16 | wholeと候補全体が異なる入力 / 32 |
| --- | --- | --- | --- | --- |
| 1 | 0 | 0 | 16 | 32 |
| 7 | 3 | 4 | 16 | 32 |
| 64 | 11 | 16 | 16 | 32 |
| 1024 | 11 | 16 | 16 | 8 |

legacy whole-inputはcp1252 exact 11/16、decode-equivalent 16/16。
64/1024がこのvalidationのtop-1件数を維持したことと、旧候補/confidence完全互換は別。
既に分析に使ったvalidationであり、未参照の独立評価と称しない。
全言語・実Webへの一般化、性能/memory、block長採用は依然として未確定。

```sh
uv run --no-project python benchmark/fixed_block_compare.py \
  /workspace/archives/v3-corpus/paris-stories-generated-1/manifest.json \
  /workspace/archives/v3-corpus/paris-full-engine-comparison-v1.json \
  /tmp/uchardet-fixed-block-build/benchmark/uchardet-fixed-block \
  /tmp/uchardet-fixed-block-build/benchmark/uchardet-conformance \
  /workspace/archives/v3-corpus/fixed-block-validation-v1.json --split validation
```

report content hash: `07945ca56191edfab5afad23c492e708849d2e64b941b5c1338d5e2c89f63c19`。
3件の追加testで、validationへのtuning/独立sample混入、保存reportの改変、
独立split指定を拒否する。新旧合わせて10件成功。

後続の[native処理コスト測定](fixed-block-timing.ja.md)では、64-byteの性能悪化が
2 runで再現した。品質件数だけで64/1024のどちらも採用可能とは判断しない。
