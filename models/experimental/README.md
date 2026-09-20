<!-- SPDX-License-Identifier: MIT -->
# 新規model generatorの最小試作

新規tool・test・本文書はMIT（`../../corpus/LICENSES/MIT.txt`）。既存tableや旧generatorをコピーせず、byte頻度と隣接byte頻度を数える独立した機構として実装しています。
**生成データの権利は別です。** sourceのlicense／reference／revision／hashを記録し、生成modelのlicenseは `UNDETERMINED` として明示します。generatorがMITでも生成物を自動的にMITと扱いません。

この試作は **uchardetへ直接投入できるmodelではありません**。runtime・既定model・CMakeへ組み込んでいません。

次段階の[SequenceModel接続契約](SEQUENCE_CONTRACT.md)では、別schemaの明示的な
tableとparametersを検証して既存構造体へ出力できます。raw byte countからの暗黙変換や
engineへの登録は行いません。

## 実行

corpus frameworkで、trainingとvalidationを元文書単位で分け、完全なcp1252 text variant（`byte_limits`にnullを含める）を作成します。

```sh
uv run --no-project python -m unittest discover -s models/experimental -p 'test_*.py'
uv run --no-project python models/experimental/model.py train /disk/corpus/manifest.json fr /disk/model.json
uv run --no-project python models/experimental/model.py emit-cpp /disk/model.json /disk/model.hpp
uv run --no-project python models/experimental/model.py score /disk/model.json /disk/corpus/manifest.json validation /disk/heldout.json
```

対象codecは最初のsingle-byte試作として **cp1252のみ**。languageごとにtraining文書だけを選び、サイズ違い・HTML・切断variantは数えません。同一source hashの二重投入を拒否し、文書間の境界を跨ぐbigramは生成しません。
外部データ取得機構はありません。testは今回作成した人工fixtureのみで、自然言語modelの品質やencoding精度の証拠にはなりません。

## 中間format

`model_format_version: 1` のcanonical JSONを正本とします。

- `symbol_counts`: byte値順の256個の非負整数
- `bigrams`: `[first_byte, second_byte, count]` をbyte組の昇順で保存する疎table
- encoding、language、固定parameter、generator version／ソースhash、corpus content hash、利用sourceのprovenance
- timestampなしのcanonical hash。JSONのkey順は固定し、encoder versionはcorpusから引き継ぎます。

整数はC++のuint64範囲を検証し、次元・重複・順序・合計値・symbol頻度との整合を確認します。
build-time C++ emitterは独立namespace内の`constexpr std::array`を出力します。testはC++11の構文と既知のfixture値を検証します。これが既存engineへのadapter互換性を保証するわけではありません。

同じ入力から別々に生成したbytesの一致（決定性）と、同じ出力先へ再実行して内容・mtimeを変えないこと（べき等性）を別testで検証します。異なるartifactへの上書きは拒否します。

## 品質評価との分離

`score`は非training splitのみを受け付け、別manifestでもtraining sourceのhash／originが混ざると拒否します。
指標はLaplace平滑化したbyte bigramの文書別bits/pairです。ゼロpair文書の値はnullです。
これは生成機構のheldout診断であり、候補ranking、language分類、文字コード正解率、confidence calibrationではありません。人工fixtureだけの場合はreportへ `synthetic_only: true` を記録します。
log計算結果はlibm等によって最下位bitが異なり得ます。決定的整数model artifactと浮動小数点品質reportを分けて扱います。

## 既存SequenceModelとの意味上の差

既存 `src/nsSBCharSetProber.h` の構造を調査すると、256-entry `charToOrderMap`、頻出文字数、文字order組の4-category `precedenceMatrix`、`mTypicalPositiveRatio`、文字種の特別値、encoding／language名を要求します。
この試作のraw byte count／bigram countには、以下がまだありません。

- 文字orderと制御文字・記号・数字等の分類
- 頻出文字の採用基準、4-categoryへの量子化とその閾値
- 既存proberのfilteringと分母に対応するpositive ratioの較正
- 実engineのcandidate ordering／confidence／incremental挙動を用いた品質比較

単に整数tableを整形して既存modelを置き換えてはいけません。次段階は自由ライセンスの自然文training／heldoutを確保し、上記の意味を明示したadapterを非デフォルトtargetへ実装し、同じengineで既存modelと比較することです。今回のmechanics testだけでmodel品質を合格扱いにしません。
