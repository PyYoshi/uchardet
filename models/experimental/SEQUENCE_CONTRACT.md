<!-- SPDX-License-Identifier: MIT -->
# SequenceModel接続契約 v1

これは独立generatorと既存engineの間の**明示的なbridge形式**であり、
model生成algorithmでも、将来のengine共通formatそのものでもない。
`model.py`のbyte-count JSONとは別schemaとし、暗黙変換を拒否する。
旧generatorやmodel tableは流用していない。

## 対象と実行

最初の対象は既存pilotと同じcp1252（alias可）のみ。engineや既定modelへは登録しない。
validator、C++11 header emitter、人工2文字modelによる構造体適合testを提供する。

```sh
uv run --no-project python -m unittest discover -s models/experimental -p 'test_*.py'
uv run --no-project python models/experimental/sequence_contract.py validate /disk/contract.json
uv run --no-project python models/experimental/sequence_contract.py emit-cpp /disk/contract.json /disk/model.hpp
```

出力headerは`nsSBCharSetProber.h`をincludeするため、compile時にnative `src`をinclude pathへ追加する。
独立namespaceの静的tableと`SequenceModel`を宣言するだけで、prober登録やlibrary target変更はしない。
同一内容への再出力はmtimeを変えず、異なる内容の上書きは拒否する。

## 必須field

| field | 契約 |
| --- | --- |
| `schema` | `uchardet-sequence-model-v1` |
| `encoding`, `language` | ASCII token。encodingはPython codecでcp1252へ正規化できること |
| `frequent_character_count` | 1〜250の整数。文字order matrixの一辺 |
| `byte_to_order` | 256整数。0〜249は文字order、251〜255は既存engineの特殊分類。250は予約 |
| `pair_categories` | 文字数の二乗の平坦なrow-major matrix。各値は0〜3 |
| `typical_positive_ratio_bits` | 正の有限値かつ1以下のbinary32を小文字8桁hexで記録 |
| `keep_english_letters` | boolean。既存構造体への格納値でありfilter切替の保証ではない |
| `generation_parameters` | character-order、pair-category、filter、ratio、文書境界の仕様/versionを明記 |
| `provenance` | generator version/license/source SHA-256、corpus content hash、training source metadata |
| `generated_model_license` | 現段階は`UNDETERMINED`。generatorのMITを生成dataへ自動適用しない |
| `content_hash` | このfieldを除くcanonical JSONのSHA-256 |

cp1252で未定義のbyteはillegal order 255でなければ拒否する。
model内のsourceはtrainingのみとし、同じhashまたはoriginの二重投入を拒否する。
validation/independent由来のsourceをmodelに含めない。

source metadataの構文検証と、その本文・許諾・生成algorithmを実際に検証することは別。
このvalidatorだけではgeneratorが申告したparametersを守ったことも、正解率も証明できない。
corpus validator、再生成比較、未使用data上の評価を別途必要とする。

## 数値と検証範囲

ratioはbinary32 bitを正本とし、C++11用には9桁のdecimal float literalを出力する。
人工値（subnormal、1/3付近、3/4、1）で、実headerを利用したcompile/runとbit一致を確認する。
testはdetectorを呼ばず、構造体field・table index・文字列を検証する。
これは候補順位、confidence較正、chunking semantics、実model精度の検証ではない。

## 次のgenerator/adapterで固定するもの

1. Unicode文字の正規化・大小文字・数字/記号/制御文字の分類、同頻度時の順序。
2. trainingのみからの頻出文字選択と、4-categoryへの量子化基準。
3. nativeが実際に受け取るfilter後の証拠量に対応したratioの計算。文書境界を跨がないこと。
4. 既存engineを呼ぶOFF-default harnessと、同一feedでの既存model比較。
5. tuningで決めた基準を固定してから未使用holdoutを開く手順。

現在のSBCS groupは`keepEnglishLetter`にかかわらず
`FilterWithoutEnglishLettersToBuffer`を適用する。flagをtrueにしただけで
全文byte bigramと推論時の分布が一致するわけではない。
同filterの互換実装を将来移植する場合は、新規MIT実装と決めつけず既存licenseを維持する。

この段階で自然文生成modelは公開しない。bridgeがcompileできたことを理由に
既存modelを置き換えたり、新しい対応encodingとして公表したりしない。
