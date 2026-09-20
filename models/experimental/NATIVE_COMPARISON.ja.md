<!-- SPDX-License-Identifier: MIT -->
# 既存 French モデルとの同条件比較

`native_comparison.py` は既存 `Windows_1252FrenchModel` と、固定したidentity/filtered
生成モデルを、同じstatic library・compiler・文書・whole-document filterで観測する。
候補ランキングや全detectorのencoding accuracyを評価するtoolではない。

```sh
uv run --no-project python models/experimental/native_comparison.py \
  /disk/identity-training.json /disk/filtered-training.json \
  /disk/validation/manifest.json validation \
  build/release/src/libuchardet.a /disk/comparison.json
```

## referenceの扱い

`sequence_probe.build_reference()` は既存extern symbolへの参照だけを持つheaderを生成する。
legacy tableをコピー、再生成、新規契約へ変換しない。
`reference_symbol`、既存source hash、実際にリンクしたlibrary hashを記録する。
生成modelの`contract_hash`や架空のtraining provenanceは割り当てない。

既存モデルのtraining corpusとの重複は未確認なので、
`legacy_training_overlap: UNKNOWN` / `training_provenance: LEGACY_NOT_VERIFIED` とする。
新規generatorのsplit分離を、legacy側の独立性の証明に使わない。
既存libraryのライセンスは維持し、MIT wrapperによる再ライセンスとは扱わない。

## 比較条件

- 新規2 profileはvalidatorを通し、同一training source/sample、Frenchであることを確認。
- tuning/validationのみ。independent sourceは本文読取り前に拒否する。
- trainingと非trainingのsource SHA/originの交差を拒否する。
- full / complete / text / cp1252を一文書一回選び、重複SHA/originを拒否する。
- 全文書65536 bytes以下。同じ3モデルに同じ検証済みbytesを渡す。
- 各モデルを別の一時binaryにbuildし、全モデルでlibrary hashが同一か確認する。
- raw/filtered長の一致を確認する。長さだけによるbyte列同値証明ではない。
  実処理は同一の既存filter関数を同一libraryからリンクして実行する。
- training時のfilter診断binaryと今回のprobe binaryは別物。両方の由来を保存し、
  source/libraryの対応は操作者が確認する。暗黙に同一buildと扱わない。

reportにはモデル名・頻出文字数、native counter/state/confidence bit、reset後の状態、
source/sample情報、build provenance、training artifact hashを保存する。
各モデルを一度buildして複数文書に使用する。通常のengine/model登録は変更しない。

## 集計の読み取り方

stateごとの文書数、有限confidenceのmin/max、負値・1超・非有限の件数を分離する。
非有限値はJSON数値へ変換せず、raw bitと件数を残す。空集合のmin/maxはnull。
高いconfidenceを高い精度と読み替えず、detectingを誤判定と数えない。
正例のFrench/cp1252だけでfalse positiveや他encodingへの識別能力は評価できない。

既存モデルのcategory0は新規profileの「未観測pair」と同じ意味とは限らない。
同名のカウンタでも学習・量子化条件を同一視しない。
生成物・観測統計はローカル保持とし、比較結果だけで標準modelへ昇格させない。
nativeテストはLinux diagnosticsで実行する。GCC/Clang系driverのみ。
fuzz・P01の保留調査を再開するものではない。
