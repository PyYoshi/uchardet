<!-- SPDX-License-Identifier: MIT -->
# 同一文章の cp1252 / UTF-8 対照評価

`paired_controls.py` はFrench validation/tuning文書のcp1252とUTF-8を対にする。
同じUnicode本文を違うencodingへ変換したときの、単一proberの反応差を見るtoolである。
全detectorのfalse-positive rateやencoding accuracyではない。

```sh
uv run --no-project python models/experimental/paired_controls.py \
  /disk/identity-training.json /disk/filtered-training.json \
  /disk/validation/manifest.json validation \
  build/release/src/libuchardet.a /disk/paired.json
```

## 選択と独立性

既存のnative比較のtraining検証・split/SHA/origin監査を先に実施する。
independent sourceがあれば本文読取り前に拒否。corpus全体のhash/codecも再検証する。
full / complete / text / cp1252の各sourceに、同じsourceのfull / complete / text / UTF-8が
ちょうど1件必要。欠損や重複を黙って除外しない。strict decodeした本文の一致も確認する。
両variantとも65536 bytes以下。HTML/切り詰めvariantを比較へ混ぜない。

## 対照の分類

- `bytes_identical`: ASCII等で同じbytesなら、識別可能な負例へ数えない。
- `control_cp1252_decodable`: UTF-8のbytesがPythonのstrict cp1252 codecでもdecode可能か。
  decode可能でも、元のUnicode本文と同じ意味とは限らない。
- `stopped_before_filtered_end`: proberの消費文字数がfilter後の長さより小さい文書数。
  confidenceが全文の統計に基づくという誤解を防ぐ。停止理由をこの値だけで確定しない。

UTF-8として妥当なbytesでもcp1252としては不正なbyteを含み得る。
構造的な拒否と、両方にdecodeできるbytes上の統計的な反応差を分離する。
decodabilityはraw bytesについてのcodec検証、途中終了はfilter後のprober観測であり、
同じ条件ではない。最終byteでの拒否等は消費長だけでは判断できない。

## 観測と集計

legacy/identity/filteredを同じlibrary・harnessでbuildし、各variantを新規proberへ一回feedする。
reportの各文書にはsample encoding、counter/state/confidence bitと由来を記録する。
encoding別のsummaryを保ち、正例と対照例のconfidenceやstateを混ぜて平均しない。

有限かつbytesが異なるpairに限り、cp1252側が高い／同値／UTF-8側が高い件数を集計する。
非有限・bytes同一は別枠。cp1252へdecode可能かによる層別集計も行う。
この順序比較は任意のthresholdを後付けで選ぶものではないが、正解率でもない。
単一proberはUTF-8候補とのランキングを行わず、内部confidenceは確率ではない。

既存modelのtraining overlapはUNKNOWN。生成modelの採用・再学習・ratio変更は行わない。
P01の全detector/大入力停止調査やfuzzを再開するtoolではない。
