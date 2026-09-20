<!-- SPDX-License-Identifier: MIT -->
# 単一モデルの native 処理時間

`model_timing.py` はlegacy/identity/filteredの3モデルを同じharness・library・corpusで測定する。
Pythonはbuild・入力選択・実行順制御だけを担当し、計時はC++の`steady_clock`で行う。
全detector、Python API、複数候補競合、マルチスレッドのbenchmarkではない。

```sh
taskset -c 2 uv run --no-project python models/experimental/model_timing.py \
  /disk/identity-training.json /disk/filtered-training.json /disk/validation/manifest.json \
  build/release/src/libuchardet.a /disk/timing.json --iterations 20000 --repeats 7
```

CPU番号は実行環境のallowed affinityから選ぶ。Linuxの1 CPU固定を要求し、未固定なら拒否する。
CPU名・governorの前後値、OS/kernel、compiler/flags、library/model/input/binaryのhashを保存する。
governorやboostを変更しない。affinityはCPUの占有、SMT相方の停止、周波数一定を保証しない。
測定中は別のbuild/test等の重い作業を実行しない。

## 計測区間

入力を一度読み、scratch bufferとproberを一度確保した後、次をC++内で繰り返す。

1. prober reset
2. 同じ全文入力を既存filterへ渡す
3. 非空のfilter結果をproberへ一回feed
4. 内部confidence取得・bit変換・volatile checksum更新

入力I/O、process起動、Python、コンパイル、入力/scratch/proberの確保、JSON出力は区間外。
128回のwarm-upも区間外。iteration数は1〜1,000,000、試行数は3〜31。
各processは10秒timeout。時間不足なら勝手にiterationを減らしたreportを出さず失敗する。

全モデルを先にbuildし、文書・試行ごとに3モデルの実行順を循環させる。
計測前の非計測観測と、各試行の最終counter/state/confidence/reset結果が一致することを検証。
checksumはconfidence bits × iteration数とも照合する。
既存filter/prober処理・table・公開APIは変更しない。

## 集計の意味

各試行の`elapsed_ns / iterations`から文書別median/min/maxを計算する。
`p95_trial_mean_ns_per_iteration`は試行平均のnearest-rank p95であり、
**リクエスト単位のp95 latencyではない**。7試行なら最大の試行平均になる。

`summed_document_trial_summary`は同じ試行番号の独立した文書別計時を合計したもの。
各文書を同じ回数評価する比較用の値で、corpusを交互に巡回する処理を実測した値ではない。
同じ文書を繰り返すためcacheが温まる。異なる文書が連続するingestion workloadへの
一般化には別benchmarkが必要である。

計時値は再実行で変動する。JSON全byteの一致を性能の再現性と扱わず、独立runの分布を比較する。
保存先はrunごとに変える。異なる既存reportを上書きしない。

## v2: 試行ごとのresource観測

Linuxでは[`getrusage(RUSAGE_SELF)`](https://man7.org/linux/man-pages/man2/getrusage.2.html)
をwall計測の直前・直後に呼び、user/system CPU時間、voluntary/involuntary context switch、
minor/major page faultの差を保存する。単一thread processの観測で、他processや子processは含めない。
counter読取りはwall区間外だが、resource差分の区間はclock読取り等を含むため厳密には異なる。
CPU時間はmicrosecond精度のtimevalをnsへ換算した値で、ns分解能を意味しない。
短い試行では0もあり得る。CPU時間がwall時間以下であることをassertしない。

report schemaは`native-model-timing-v2`。各sourceの`trial_resources`配列は`elapsed_ns`と
同じ試行順・件数で、全試行を除外せず保存する。Linuxのresource取得失敗は計測失敗とする。
non-Linuxの低レベルprobeは`resources: null`とし、未観測値を0と偽らない。
Linux affinity必須の上位runnerはresourceが欠けた場合にreport生成を拒否する。

CPUとwallの差やcontext switchの増加は原因調査の材料であって、個々の停止時間や
周波数・cache missの計測ではない。相関だけでOSやmodelを原因と断定しない。
新しいcounterを理由に試行を自動削除したり、過去reportを補完したりしない。

## 採用判断とは別

このtoolは単一モデルのreuse処理コストだけを測る。allocation数、ピークmemory、
モデル生成時間、全detectorのthroughput/候補順位は未測定。
新規モデルの品質・権利・confidence校正は別gateであり、速さだけで採用しない。
CIの短い反復は計測機構と出力一致のtestで、性能数値を主張するものではない。
