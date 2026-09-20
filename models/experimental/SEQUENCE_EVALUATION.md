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

## v2: 文書平均と入力サイズ別集計

`sequence-coverage-evaluation-v2`では従来のmicro集計を残し、
`macro_rates`と`size_strata`を追加します。training artifact・table・profileは変更しません。

`macro_rates`は各指標について、分母が正の文書だけを等しい重みで平均します。
平均は既約分数の`numerator`/`denominator`で保存し、浮動小数点丸めを含めません。
`defined_documents`と`undefined_documents`を併記します。分母0を率0として
含めず、有効文書が0件ならmeanはnullです。分子0・分母正の文書は有効です。
これは文書単位の記述統計であり、文書間の統計的独立性を仮定した信頼区間ではありません。

`size_strata`は完全なcp1252文書のbyte長で分類します。下端inclusive、上端exclusiveで、
境界は0 / 16 / 32 / 64 / 128 / 256 / 512 / 1024 / 4096 / 16384 / 65536 /
262144 bytes、最後の上端はnull（無制限）です。空文書は最初の区間に入り、
ちょうど16 bytesなら次の区間です。各区間に文書数、micro counts/rates、macro ratesを持ちます。
空区間も文書数0、counts 0、rates nullとして明示します。

この分類のために文書を切断・複製したり、新しいvariantを作ったりしません。
区間のcountsを足すと全体countsに一致し、文書境界を跨ぐpairは増えません。
同じsourceを異なる長さで切った場合のevidence量比較とは別の分析です。
長文micro平均と短文を含む文書平均の差は分布の偏りを示しますが、
detector accuracyやconfidence較正、母集団の代表性を証明しません。

v1 reportのfileは保持し、v2は別出力先へ保存してください。schemaとevaluator依存hashが
変わるためcontent hashも変わります。旧reportを再現する場合は生成時のrevisionを使用します。

### 保存済み会話corpusでの確認（2026-09-21）

Paris Stories validation 16文書に対し、固定training artifact
`856a8ba06a4a6d8450ddb3f4afeafdf99223a2c715350ce6e381a8e271c80515`を再学習せず使用しました。
v1の全document観測とaggregate countsが一致し、全16文書は[1024,4096) bytesでした。
このcorpus単独では短文・大文書の比較ができないことを明示します。
新しいnative予測・独立holdout評価は実行していません。

French Tatoeba pilotへの同じ診断は、複数文が共通originを持つため既存の
`duplicate selected evaluation source hash/origin`検証で拒否されました。
成功reportは生成せず、origin制約を緩めたり本文を結合したりしていません。
録音／文書／例文の集計単位とsource groupの違いは、別途契約を決める必要があります。

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
