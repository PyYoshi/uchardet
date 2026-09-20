<!-- SPDX-License-Identifier: MIT -->
# 固定ratioモデルのchunk比較

感度実験で選んだ因子0.90を動かさず、同じtuning 8録音のfull cp1252/UTF-8全16入力を
whole / 1 / 7 / 64 / 1024-byte chunkで観測する。各入力4 KiB以下・各process10秒上限。
標準legacy、identity/filteredの因子1/0.90を比較し、全400観測を保存する。
因子やtableを調整する試験ではなく、incrementalの採用gateを確認する試験。
大入力、追加fuzz、P01対象の停止調査は行わない。

## 比較の分離

- 同じmodelのwholeとの差。
- 同じchunk scheduleのlegacyとの差。
- 同じprofile・同じchunk scheduleの因子1との差。

各比較で候補数、encoding/language順序、confidence bitsを含む候補一覧、final done、
first done offsetを別に記録する。feed回数はchunkにより必然的に変わるので差分指標には
含めず、生観測に保持する。first done offsetはfeed後に観測した位置で、内部の厳密な
最初の判定byte位置を表すとは限らない。完全一致を近似float比較へ置き換えない。

## 結果

cp1252のstrict decode-equivalent件数（各8入力）:

| chunk | legacy | identity 1 | identity 0.90 | filtered 1 | filtered 0.90 |
| --- | ---: | ---: | ---: | ---: | ---: |
| whole | 8 | 4 | 8 | 5 | 8 |
| 1 | 0 | 0 | 0 | 0 | 0 |
| 7 | 6 | 4 | 4 | 4 | 4 |
| 64 | 8 | 4 | 7 | 5 | 8 |
| 1024 | 8 | 4 | 8 | 5 | 8 |

UTF-8 exactは全model・全scheduleで8/8。全出力confidenceは有限かつ[0,1]内だった。
wholeに対する候補完全一致の不一致件数は、1/7/64-byteで各modelとも16/16、
1024-byteで各modelとも4/16。encoding/language順序の不一致とは分けてreportへ保持する。
final done / first done offsetのwholeとの差は今回すべて0件。

1-byteの悪化はlegacyにも存在し、今回のratio変更だけに起因するとは言えない。
一方、7-byteでは生成modelがlegacyより悪く、wholeの8/8だけで標準採用する根拠にはならない。
因子0.90は小規模whole-inputの候補のままとし、incremental gateを達成したとは扱わない。
この結果を見てtuning gridを増やさない。具体的な原因は別途追跡する。

## 再現

```sh
uv run --no-project python models/experimental/ratio_chunks.py \
  IDENTITY FILTERED MANIFEST SWEEP BUILDS OUTPUT
```

入力は24録音版の親artifact、training/tuning manifest、固定ratio sweep report、
その検証済みbuild directory。sweep hash、親model、入力hash、source/binaryを照合する。
wholeの4生成model観測は保存sweepと完全一致を要求する。
複数buildの標準targetも各入力・chunkで完全一致を要求する。

private report: `archives/v3-corpus/paris24-ratio-chunks-v1.json`。
content hash: `5d28f112f1ed472e1a438df9790f9e2f50c9aa0e216943059e2bb51621d0c8c1`。
生観測、3種類の差分、accuracy、buildの参照元sweep hashを保存している。
全条件を2回観測してreport全体のbyte一致を確認した。
今回の評価対象はtuningであり、独立汎化精度の主張ではない。
