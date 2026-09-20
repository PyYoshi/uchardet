<!-- SPDX-License-Identifier: MIT -->
# SBCS filter入力契約の診断

`uchardet-filter-profile`は既存の`FilterWithoutEnglishLettersToBuffer`を呼び出し、
filter前後のbyte統計をJSONへ出力する開発用toolです。filterを移植・再実装せず、
detector、model、公開APIを変更しません。tool/test/本文書は独立したMIT実装です。
リンク先のengineとfilterの既存licenseは変更しません。

## 実行

```sh
cmake --preset release -DBUILD_INTROSPECTION=ON
cmake --build --preset release --target uchardet-filter-profile
build/release/benchmark/uchardet-filter-profile 0 /disk/sample.bin
UCHARDET_FILTER_PROFILE=build/release/benchmark/uchardet-filter-profile \
  uv run --no-project python -m unittest discover -s benchmark -p test_filter_profile.py
```

staticな開発build限定、既定OFF、install対象外です。入力は1ファイル最大65,536 bytes。
chunkは0（全文）または1〜65,536の整数。空入力ではfilterを呼びません。
観測前に別途入力・実行binaryのSHA-256とnative revisionを記録してください。
tool自身は入力file名・本文・hex dumpを出しません。ただしbyte/pair頻度も入力由来の
情報を含み、特に短文では内容を推測できるため、匿名化済みデータとは扱わないでください。

## 出力契約

- `schema`: `sbcs-filter-profile-v1`
- `chunk_size`: 指定したchunk（0は全文）
- `raw` / `filtered`: 元入力と、各filter呼出しの出力を順番に連結した列の統計
  - `bytes`: byte数
  - `symbols`: byte値0〜255順の256個の整数頻度
  - `pairs`: `[first_byte, second_byte, count]`をbyte組の昇順に並べた疎table
- `calls`: 各呼出しの`[input_length, filtered_length]`

pairはこの1文書の連結列で数えるので、空でないfilter出力同士のfeed境界も跨ぎます。
別文書を同じ呼出しへ連結してはいけません。これは生byteの隣接pairであり、modelの
文字order、matrix分類、sequence counter、confidenceの分母とは異なります。
raw側はchunkによらず同じ統計ですが、filter後の列はchunkで変わり得ます。

小fixtureのcp1252 `plain café text`（15 bytes）では、全文filterの結果は
`café `（5 bytes）相当、1-byte chunkの連結結果は`é`（1 byte）相当です。
これは既存filterの観測であり、chunk差分を修正する変更ではありません。

## 保証しないこと

このtoolはgroup/proberのactive状態、文字種order変換、early completionを実行しません。
実際のdetectorが文書の全chunkを同じchildへ渡したことも証明しません。
そのため、この統計だけでfilter互換training、confidence較正、精度改善を合格にしません。
既定profileの`identity-unfiltered-v1` / `NOT_ENGINE_CALIBRATED`は維持します。

testは空/ASCII、小さなaccent語、既存135-byte日本語fixtureとCLI引数を対象とします。
追加fuzz、大入力の停止原因調査、BOM試作評価、独立holdout予測は行いません。
