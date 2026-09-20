<!-- SPDX-License-Identifier: MIT -->
# 固定SequenceModel tableのPython-only coverage診断

このtoolは学習済みの実験tableを変更せず、tuning／validation本文がどれだけtableの
文字・pair範囲に収まるかを数えます。**encoding accuracy、detector、confidenceの
評価ではありません。** `NOT_ENGINE_CALIBRATED`を維持し、native実行・compile、
filter互換実装、engine登録、P01の再開は行いません。

## 実行

```sh
uv run --no-project python -m unittest discover -s models/experimental -p test_sequence_evaluation.py
uv run --no-project python models/experimental/sequence_evaluation.py \
  /disk/training.json validation /disk/coverage.json /disk/evaluation/manifest.json
```

複数manifestは最後に列挙できます。splitは`tuning`か`validation`のみです。
`training`と`independent`は拒否します。独立holdoutの予測・category診断は行いません。
testは人工fixtureとPython subprocessのみで、実データの評価は含みません。

## 選択と漏洩監査

training artifactは既存の厳密validatorで検査します。source依存hash／runtimeの固定と、
document countsからのtable再計算が有効です。ただし、この評価toolはtraining元本文を
読み直すものではありません。必要なら生成toolの`validate --manifest`で別途照合します。

評価manifestはcorpus frameworkでsource・sampleの実byteを再検証します。
入力manifestの全sourceについて、training artifactに含まれるsourceと他manifestのsource
を突き合わせ、同じSHA-256またはoriginが異なるsplitへ入っていれば拒否します。
選択外language・variant・splitもこの漏洩監査の対象です。manifest内の独立holdoutは
通常のcorpus整合性検証の対象にはなりますが、model tableへの照合対象にはしません。

診断対象はmodelと同じlanguage、指定split、cp1252、text、complete、byte_limit=null
のsampleだけです。HTML・短縮・切断variantを重複して数えません。
選択sourceのhashまたはoriginの二重投入と、同一manifestの重複指定は拒否します。
有効対象が0件なら空の成功reportではなくエラーにします。
同一splitにある似た文章の検出や権利条件の審査は、このhash／origin監査とは別作業です。

## countと分母

`filter_profile=identity-unfiltered-v1`で、byteを削除・連結せず直接の隣接だけを扱います。
cp1252はsingle-byteなので、ここでのletter出現数はUnicode L*に分類されるbyteの出現数
です。異なる文字種の数ではなく、出現頻度で重み付けしたcoverageです。

| count | 意味 |
| --- | --- |
| bytes | 対象sampleの全byte数 |
| letters | letterの全出現数 |
| frequent_letters | orderがfrequent_character_count未満のletter出現数 |
| known_rare_letters | trainingには出現したが頻出文字table外のletter出現数 |
| unknown_letters | trainingで出現しなかったletterの出現数 |
| adjacent_letter_pairs | 文書内で直接隣接し、両方letterであるpair出現数 |
| matrix_pairs | 上記のうち両方が頻出文字であるpair出現数 |
| outside_matrix_pairs | 片方以上が低頻度／未知letterであるpair出現数 |
| category_mass | matrix pairを固定tableのcategory 0／1／2／3へ分類した4整数 |
| unseen_matrix_pairs | 固定profileでcategory 0に置かれた未観測matrix pairの出現数 |

`letters = frequent_letters + known_rare_letters + unknown_letters`、
`adjacent_letter_pairs = matrix_pairs + outside_matrix_pairs`、
`matrix_pairs = sum(category_mass)`が成り立ちます。
matrix外pairをcategory 0に混ぜません。category 0を未観測と扱えるのは、既存の固定
training profileを検証しているためであり、任意の旧modelについての仮定ではありません。

各documentと合計のrateは浮動小数点ではなく`numerator`／`denominator`で保存します。
frequent／known-rare／unknown letter率の分母はletters、matrix coverageの分母は
adjacent_letter_pairs、unseen matrix pair率の分母はmatrix_pairsです。
分母0はnullです。合計はdocument別countsを足したmicro集計であり、documentごとの
比率平均ではありません。文書を連結しないため、文書を跨ぐpairは生成しません。

## 再現情報と限界

reportには全監査manifest hash、実際に診断したsource metadata・sample hash・encoder
version、training artifact hash、model契約hash、runtime、evaluator自身を含む依存source
hash、filter profile、対象source数、synthetic_onlyを保存します。本文は出力しません。
manifest列挙順に依存しないcanonical JSONとcontent hashを出力し、同じ結果の再出力は
mtimeを維持します。異なる結果で既存fileを上書きしません。

小さい人工fixtureの手計算、未知／低頻度文字の区別、未観測pair、空分母、文書境界、
split漏洩、variant除外、改変sampleの拒否をtestします。
coverageが高くてもencodingの識別能力やconfidence較正は保証しません。
95%／99%の量子化閾値をここで調整したり、validationに合わせて再trainingしたりはしません。
診断を読んで将来parameterを調整した場合、そのvalidationを未使用holdoutとは呼べません。
