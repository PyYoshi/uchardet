<!-- SPDX-License-Identifier: MIT -->
# native filter 入力に基づく実験的 SequenceModel 生成

`filtered_training.py` は既存の identity profile を変更せず、別の
`cp1252-native-filter-sequence-training-v1` を生成する。
旧 `script/` の generator は使わない。公開 engine/model へ登録しない。

## 実行

```sh
cmake --preset release -DBUILD_INTROSPECTION=ON
cmake --build --preset release --parallel 2
uv run --no-project python models/experimental/filtered_training.py train \
  /disk/training/manifest.json fr build/release/benchmark/uchardet-filter-profile \
  /disk/filtered-training.json
uv run --no-project python models/experimental/filtered_training.py validate \
  /disk/filtered-training.json --manifest /disk/training/manifest.json \
  --binary build/release/benchmark/uchardet-filter-profile
```

入力は corpus framework の manifest。training split の full / complete / text /
cp1252 のみ選ぶ。independent source を含む manifest は本文を読む前に拒否する。
必要なら元 manifest の **training source metadata のみ**から framework で別 corpus を
生成する。元の split を書き換えたり、独立 holdout を再分類したりしない。
一文書 65536 bytes 以下。超過時は暗黙の切り詰めや chunk 化をせず失敗する。

## 処理と由来

1. corpus framework で本文・codec・hash を再検証する。
2. 選択された検証済み bytes を一時ファイルへ渡す（最大64 KiB）。
3. 既存 native tool の `chunk_size=0` で文書全体を一回 filter する。
   各 subprocess の timeout は10秒。detector/prober は実行しない。
4. native raw 統計を Python 側の入力 bytes の統計と独立に照合する。
5. filtered 統計から identity profile と同じ文字順・95/99%量子化・binary32丸めを
   用いてテーブルを導出する。文書間 pair は作らない。
6. `keep_english_letters=False`、filter 名、whole-document 条件、実行 binary SHA-256、
   generator/filter source の依存hash、Python/Unicode版、元source・sampleの由来を保存する。

native binary hash は生成前後にも照合する。これは実行した binary の識別情報であり、
指定 binary が当該 source からビルドされたことの証明ではない。
利用者は記載されたビルド手順で作成した信頼する tool を指定する。

`validate` 単独は保存した統計からのテーブル再導出・由来の整合性を確認する。
統計だけから元の bytes や filter 実行を証明するものではない。
`--manifest` と `--binary` を併用すると、corpus から native 観測をやり直して
artifact 全体を照合する。異なる binary/build の結果は同一 artifact と扱わない。
保存は既存の排他的・べき等 helper を使用し、異なる既存ファイルを上書きしない。

## まだ保証しないもの

- `NOT_ENGINE_CALIBRATED` のまま。filtered byte pair と実際の prober の sequence counter
  は同じとは限らず、confidence ratio の校正は別工程。
- incremental chunking、early termination、active/rejected prober の再現ではない。
- encoding/language 精度の改善や legacy model より優れることを示していない。
- `keep_english_letters=False` は実験契約上の指定であり、本番登録の承認ではない。
- 生成物の license は `UNDETERMINED`。モデル・観測統計を repository へ公開しない。
  頻度情報は匿名化ではない。

実 native tool のテストは `UCHARDET_FILTER_PROFILE` 指定時に実行する。
CI の Linux diagnostics job でも有効にする。他の環境では純 Python 検証のみ。
