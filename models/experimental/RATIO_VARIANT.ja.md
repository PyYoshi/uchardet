<!-- SPDX-License-Identifier: MIT -->
# French生成モデルのratio感度実験（事前固定）

目的は、固定した生成modelのconfidence scaleが候補競合に与える影響を切り分けること。
確率としてのconfidence calibrationや標準採用を完了する実験ではない。
旧model・engine共通の係数・category table・byte orderは変更しない。

## 予測前に固定する条件

- training: Paris 24録音版の固定identity / filtered artifact。
- tuning: 残り8録音、full cp1252/UTF-8の全16入力。各4 KiB以下、fresh/one-shot。
- ratio因子: 1、19/20、9/10、4/5の4通り。追加探索はこの実験ではしない。
- 2 profile × 4因子を全て報告し、良いものだけ掲載しない。
- 各因子は親ratioに適用し、前のvariantへ累積適用しない。
- factor 1はmodel contractをbyte単位で維持する対照。
- 判定対象は先頭候補のexact codec / decode-equivalent / language、正解codec候補内存在。
- 全candidateのconfidence bits、done、候補数・順序を保持する。
- 各processは10秒上限。timeout/errorを成功・不一致の集計に紛れ込ませない。
- validationと独立holdoutへ新たな予測を行わない。P01は再開しない。

## 次段階へ進める条件

同じprofileのfactor 1に対し、cp1252のdecode-equivalentが1件以上改善し、
UTF-8 exact/decode-equivalent、両encodingのlanguage一致件数に悪化がないこと。
全出力confidenceが有限かつ[0,1]内にあることも要求する（clampしない）。
複数候補が満たす場合はcp1252 decode-equivalent、exact codec、factorが1に近い順で選ぶ。
いずれも満たさなければこのgridの結果は不採択。候補を増やして同じtuningへ再挑戦しない。
1件改善でも標準採用を意味せず、未使用data・性能・incremental等のgateは残る。
元modelのconfidenceは保証された確率ではなく、ratioを下げる操作は負の値にも作用する。

## Artifact

`ratio_variant.py PARENT FACTOR OUTPUT`で私的なvariant artifactを作る。
親training artifactは既存generatorのvalidatorで再検証し、任意のmodel tableを受け入れない。
親artifact hash、固定因子、変換tool hash、派生contractを記録する。
`validate(variant, parent)`は変換を再計算して完全一致を要求する。
licenseはUNDETERMINEDのまま、deployment statusはSENSITIVITY_ONLY_NOT_CALIBRATED。
このartifactを元のtraining artifactとして扱ったり、元validatorを緩めたりしない。

`ratio_sweep.py IDENTITY FILTERED MANIFEST BASELINE BUILDS OUTPUT`で全条件を実行する。
BASELINEは事前固定した`paris24-tuning-engine-v1.json`で、content hashを固定値と照合する。
MANIFESTと親artifactもbaselineに記録されたhashへ固定する。
既存buildはcontract/source/binaryの完全照合後のみ再利用する。途中で失敗したbuildを
削除・上書きして自動再開する処理はない。新しい出力report名を指定して再観測できる。
因子1と標準targetは保存baselineと完全一致を要求する。
この文書は結果を観測する前の仕様であり、実測結果と採否は別文書へ記録する。
