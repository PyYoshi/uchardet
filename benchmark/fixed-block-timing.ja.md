<!-- SPDX-License-Identifier: MIT -->
# 固定block adapterのnative処理コスト

## 範囲と比較方式

第3試作のwarm reuse計測。Python処理・process起動・入力I/O・初期detector/buffer確保を
計測外にし、reset・feed・finalize・候補数/先頭encodingの最小限の結果取得を計測する。
標準modelの同じstatic libraryへlinkした一つのbinaryで以下を比較する。

1. `whole`: 入力全体を直接nativeへ渡す。
2. `direct_fixed`: adapterと同じ固定blockを直接nativeへ渡す。
3. `adapter`: 外部chunkをadapterで正規化してnativeへ渡す。

wholeとの比較は候補/confidence等の動作差を含む。direct_fixedとの差は主にadapterの
buffer copy/外部feed処理に対応するが、microbenchmarkの揺らぎを因果証明とはしない。
CIは短い入力のschema・checksum・引数検証だけを実行し、速度閾値をassertしない。

## 固定条件

- corpus: 固定tuningのcp1252/UTF-8各8入力、計16入力、各4096 bytes以下。
- 内部block 1/7/64/1024、外部chunk whole/1/64。結果による候補追加なし。
- CPU2へaffinity固定。各入力100反復×7試行、各方式17 warmup。
- 3方式の順番は試行ごとに循環。各native processは10秒timeout。
- C++ steady_clockで計測。checksumは候補数と先頭encodingの先頭byteに基づく。
  checksum一致は候補全体の同等性証明ではなく、完全比較は別のconformance評価で行う。
- GCC 16.2.1、CMake Release、C++11、`-msse2 -mfpmath=sse -O3 -DNDEBUG`。
- 計測中に別のbuild/testを実行しない。hostの他process・SMT相方・周波数は固定しない。
  確認時のgovernorはpowersave。affinityをCPU占有と称しない。

## 初回結果（2026-09-22）

数値は文書別trial平均を合計した7試行のmedian、単位ms。
同じ文書のwarm cache測定の合計であり、異なる文書を順次処理するcorpus passではない。

| 内部block / 外部chunk | whole | direct_fixed | adapter |
| --- | ---: | ---: | ---: |
| 64 / whole | 10.4270 | 11.1460 | 11.1323 |
| 64 / 1 | 10.4268 | 11.1544 | 11.3727 |
| 64 / 64 | 10.4269 | 11.1194 | 11.1388 |
| 1024 / whole | 10.4053 | 10.4694 | 10.4829 |
| 1024 / 1 | 10.4064 | 10.4893 | 10.7285 |
| 1024 / 64 | 10.4039 | 10.4877 | 10.4781 |

64のadapterはwhole比で約6.8〜9.1%遅く、開発計画の5%調査閾値を超えた。
1024は約0.7〜3.1%。「1%以内」は外部whole/64に限り、外部1-byteへ一般化しない。
初回結果だけでblock採用・性能gate通過を決めない。追加runで再現性を確認する。
requestごとのp95、初回確保、allocation数、peak/live memoryは未測定。

文書別medianでも確認した。外部whole時、64のadapterは16入力中14件でwhole比5%超、
範囲は+4.76〜9.30%。1024は16入力とも5%以下（+0.28〜1.24%）だった。
sumのmedianと文書別medianは異なる集計であり、両方を保存結果から確認する。

## 同条件の2回目

同じbinary・driver・入力・affinity・反復数で再計測した。終了後のgovernorもpowersave。

| 内部block / 外部chunk | whole | direct_fixed | adapter |
| --- | ---: | ---: | ---: |
| 64 / whole | 10.4233 | 11.1432 | 11.1145 |
| 64 / 1 | 10.4375 | 11.1443 | 11.3852 |
| 64 / 64 | 10.4195 | 11.1211 | 11.1264 |
| 1024 / whole | 10.4047 | 10.4735 | 10.4649 |
| 1024 / 1 | 10.4144 | 10.4823 | 10.7153 |
| 1024 / 64 | 10.4153 | 10.4980 | 10.4942 |

外部wholeの文書別medianは、64で16入力中15件が5%超（+4.84〜8.55%）、
1024で5%超なし（+0.19〜1.15%）。64の5%超悪化は再現したため、
今回のまま標準採用する根拠にはしない。direct_fixedでも増分があるため、
adapterのcopyを削るだけで差を解消できると仮定しない。
1024は追加評価候補に残せるが、これはmemory・request p95・全言語での採用gate通過ではない。
速度で有利な1-byteの品質後退を無視して採用することもしない。

run2 content hash: `228857d6ec5f75488c3a66fd0b8faee90862b44456e9c4b727b3f62b1ba30b6c`。
全12条件の生データは各reportに保存しており、表から省略した1/7-byte条件も削除していない。

## 再現・保存

```sh
cmake --build /tmp/uchardet-fixed-block-build --target uchardet-fixed-block-timing
UV_CACHE_DIR=/tmp/cchardet-v3-uv taskset -c 2 uv run --no-project python benchmark/fixed_block_timing.py \
  /workspace/archives/v3-corpus/paris-training-tuning-generated-v1/manifest.json \
  /workspace/archives/v3-corpus/fixed-block-tuning-v3.json \
  /tmp/uchardet-fixed-block-build/benchmark/uchardet-fixed-block-timing \
  /workspace/archives/v3-corpus/fixed-block-timing-run1.json
```

`/workspace`は実際の保存先へ置き換える。時間の全byte一致は要求せず、全試行を保存する。
reportは入力・binary・driver hash、uname、affinity、試行平均とchecksumを含む。
run1 content hash: `bd9e9141081efa6d36f7b34e7494ae74115be9359b650826c12136f8e4526cc8`。
binary hash: `ee9b4632384c653e5ade9542d2e884508421db60855e4c51669d8cf625ac32a6`。
driver hash: `beec60ff4c8852e496856351b7c455adafae5ebbb0c97c0a4a113189df92933d`。

非デフォルト実験のみ。P01の大入力・追加安全性検証や独立holdout開封は行っていない。
