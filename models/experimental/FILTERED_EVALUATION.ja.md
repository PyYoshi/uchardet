<!-- SPDX-License-Identifier: MIT -->
# 同じ filter 入力での固定モデル比較

`filtered_evaluation.py` は同じ training source / sample bytes から生成した identity と
native-filter profile を、同一の native-filter 観測に対して比較する。
再学習・しきい値調整は行わない。これは encoding accuracy / confidence の評価ではない。

```sh
uv run --no-project python models/experimental/filtered_evaluation.py \
  /disk/identity-training.json /disk/filtered-training.json \
  /disk/validation/manifest.json validation \
  build/release/benchmark/uchardet-filter-profile /disk/comparison.json
```

## 固定条件

- tuning または validation だけを選択する。independent source が manifest にあれば、
  corpus validator が本文を読む前に拒否する。
- training source の SHA/origin と非training source の交差を metadata で拒否する。
- full / complete / text / cp1252 の source を一回だけ評価する。
  選択sourceの同一SHAや同一originの重複は拒否する。
- source origin が corpus 全体の共通グループ名の場合も自動的に文書IDへ変更しない。
  そのような corpus は現在の比較profileでは扱わず、将来のgroup単位評価設計を別に行う。
- training時と同じ native binary SHA-256 を要求する。各文書65536 bytes以下、
  whole-document filter、一呼出し10秒timeout。binaryを前後に照合する。
- filter観測は一文書につき一回だけ行い、両テーブルへ同じ統計を渡す。

## 指標

既存 coverage evaluator と同じ letter 分類・matrix 内外・未観測pairを、
native観測のsymbol/pair頻度から計算する。小fixtureではbyte列からの直接計算と照合する。
この profile では category 0 は training 未観測matrix pairを表す。

全体の整数分子/分母（micro）と、算出可能な各文書の比率の単純平均（macro）を別々に保存する。
空の証拠では率を `null` とし、macroの算出可能/不能文書数を記録する。
サイズ区分は **filter前のraw文書サイズ**。集計する文字・pairはfilter後であり、混同しない。
corpusは一manifestごとに出力し、異なるcorpusを一つの正解率へ混ぜない。

出力は観測統計、source/sample由来、元corpus/modelのhash、generator/evaluator依存hash、
runtimeと実行binaryを持つ。同一入力への再実行は同じ出力ならmtimeを維持し、
異なる既存出力は上書きしない。別出力との全byte比較でも再現性を検証できる。
統計は匿名化ではなく、生成modelと同様にローカル保持を基本とする。

## 読み取り方

両モデルのfilter後inputは同じだが、training inputはidentityとfilteredで意図的に違う。
「native filterへ合わせたから品質が上がる」とは仮定しない。
filterによって学習証拠が減れば文字・pairのcoverageが下がる可能性がある。
category質量の大小をconfidenceや正解率に読み替えない。

proberのsequence counter、early termination、候補競合、confidence校正、実encoding正解率は
別工程。`NOT_ENGINE_CALIBRATED` を維持し、標準model登録の根拠にはしない。
