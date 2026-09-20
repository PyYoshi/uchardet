<!-- SPDX-License-Identifier: MIT -->
# v3 corpus 基盤（schema version 1）

[source 本文の重複監査](OVERLAP.md)で、metadata だけでは見えない正規化一致・近似一致を診断できます。

このディレクトリの新規tool・test・文書は `LICENSES/MIT.txt` に従います。
既存detector、model、外部corpusを再ライセンスするものではありません。

Python 3.11以上の標準ライブラリだけで動き、network取得・暗黙の文字置換・既存出力の上書きを行いません。

```sh
uv run --no-project python -m unittest discover -s corpus -p 'test_*.py'
uv run --no-project python corpus/framework.py generate /disk/input/config.json /disk/corpus-v1
uv run --no-project python corpus/framework.py validate /disk/corpus-v1/manifest.json
uv run --no-project python corpus/framework.py audit-splits /disk/training/manifest.json /disk/independent/manifest.json
```

## 入力契約

configは次の形のJSONです。`sha256` は入力UTF-8ファイルの実際のSHA-256へ置き換えます。
pathはconfigのあるディレクトリ基準で、絶対path、親への移動、root外へのsymlinkを拒否します。

```json
{
  "sources": [{
    "id": "example-v1", "path": "example.txt", "language": "fr",
    "license": "MIT", "license_reference": "LICENSE.txt",
    "revision": "fixture-v1", "origin": "synthetic:example-document",
    "kind": "synthetic", "sha256": "REPLACE_WITH_SHA256",
    "split": "validation"
  }],
  "encodings": ["utf-8", "cp1252"],
  "byte_limits": [null, 16, 64, 1024],
  "boundaries": ["complete", "truncated"],
  "formats": ["text", "html-clean", "html-declared", "html-mismatched"]
}
```

- sourceはUTF-8で読み、改行やUnicode正規化を自動変更しません。
- `origin` は元文書の安定した識別子、`revision` は固定した版です。異なる版でも同じoriginを維持します。
- `license` と `license_reference` は必須ですが、文字列の存在は権利確認の代わりになりません。取得・再配布の可否を確認してから入力してください。toolは許諾判断や外部URL取得をしません。
- splitは `training` / `tuning` / `validation` / `independent`。同一manifest内の同一source hashまたは同一originがsplitを跨ぐと拒否します。別々のmanifestを利用する場合は全partitionを `audit-splits` に渡してください。言い換え・別originの類似文書までは検出しません。
- kindは `synthetic` / `natural`。test内の文章は今回作成した人工fixtureであり、自然文のmodel学習・精度benchmarkには使いません。

## 出力と再現性

出力は `sources/` の元UTF-8、`samples/` のbyte列、`manifest.json` です。
sourceの由来・hash・言語・splitを保持し、sampleからsource IDで参照します。
sampleには実encoding、encoder (`python-codecs`)、Python実装/version、byte limit、実byte長・文字数・hashを記録します。
新規sampleの `ground_truth` は `provenance: "strict-source-reencoding"` と `certainty` を持ちます。
`certainty` は実際にbyte切断が起きた場合 `"byte-truncated"`、それ以外は `"strict-roundtrip"` です。
これは生成ラベルの由来であり、短いASCII等の入力から一意にencodingを判定できる保証やdetectorのconfidenceではありません。
`truncated` を指定しても上限に達しなければ `strict-roundtrip` です。従来のschema 1 manifestはこのfieldや生成reportがなくても検証できます。
Python codec環境が違えば同じ結果を保証しません。再現時はPython versionも固定してください。

`content_hash` はsortしたUTF-8 JSONを用い、`content_hash` 自身と任意の運用記録 `generated_at` を除外します。
生成時刻を自動注入しないため、同じ入力・同じ環境で別出力先へ再実行すれば同じmanifestになります。
更新時は新しい出力先を使いhashを比較します。生成失敗時に出力ディレクトリが残る場合は失敗artifactとして扱い、manifestのない出力は使用しないでください。

## 生成失敗の記録と母数

既定の `fail-fast` は従来通り、1件でもencode／往復変換に失敗すれば出力前に停止します。
多言語sourceと複数codecの組み合わせを列挙する場合は明示的に次を指定できます。

```sh
uv run --no-project python corpus/framework.py generate /disk/input/config.json /disk/corpus-v2 --failure-policy record-and-continue
```

`record-and-continue` が継続するのはstrict encodeの `UnicodeEncodeError` と、codecの非往復mappingだけです。
未知codec、非text codec、不正format／boundary／byte limit、重複variant、source hash不一致、UTF-8 source不正、I/O障害、64 MiB超過等は停止します。
encodeできる短いprefixへの置き換えや `ignore` / `replace` は行いません。

新規manifestの `generation_report` に次を保持します。

- `dimensions`: 正規化したcodec名とformat／boundary／byte limit。source一覧との直積が試行母数です。
- `failure_policy`: 今回の方針。
- `counts`: `attempted` / `successful` / `skipped`。全件skipでもsourceとreportを出力し、成功件数0を明示します。
- `attempts`: 全variantのsource ID／codec／format／limit／boundaryと `status`。成功は `sample_id`、skipは決定的な `reason` (`unencodable` / `non-roundtrip`) を持ちます。

`validate` は直積に対する記録の網羅性、sampleとの対応、件数、skip理由を元sourceから再計算します。
reportはmanifestのcontent hashにも含まれます。ただし元configと一緒に全体を改変した場合の真正性保証ではありません。実験時は元configとmanifest hashも別途固定してください。
skipはdetectorの誤判定ではなく「指定変換ではfixtureを生成できなかった件数」です。生成済みsampleだけの精度を全試行の精度と見なさず、評価reportでは生成母数とskip件数を併記してください。このtool自体は予測や期待正解率を算出しません。

## manifest間のsplit監査

`audit-splits` はmanifest JSONのschema、content hash、source metadataと、全manifestを跨ぐorigin／source hashのsplitを確認します。
同じsource IDが別manifestにあること自体はエラーではありません。同じoriginの別revisionや別IDの同一hashがsplitを跨ぐ場合に拒否します。
成功時はmanifest数、source record数、`split_leakage: false` のJSONを標準出力します。失敗時は非zero exitです。

Pythonからは `audit_manifests(paths: list[Path])` を利用できます。
これはmetadataだけの監査であり、source／sample本文の読み込み、detectorの起動、holdoutの予測・精度評価は行いません。
実byteの整合性確認には別途 `validate` が必要です。metadata hashは権利確認・真正性・近重複の保証でもありません。

## byte limitとHTML

- `complete`: strict encode/decodeで往復可能なUnicode接頭辞を選びます。ISO-2022-JPの終了escapeやBOMも上限に含めます。BOMすら収まらない場合は空byte列・文字数0です。サイズは厳密一致でなく上限です。
- `truncated`: 元の完全encode結果をbyte境界で切ります。壊れた末尾も意図的に保持し、文字数はnullです。指定していても上限が十分なら実際の切断は起きません。
- 元文章全体がencodeできない場合は、短いprefixがencode可能でも失敗します。`ignore` / `replace` を使いません。codecによる非往復mappingも拒否します。
- completeの接頭辞探索ではincremental encoderのstateを複製して終了byte数を確認し、最後に選択した接頭辞を一括encodeして再検証します。各byte limitについて全文を走査するため、大量のvariant生成では生成コストも計測してください。
- HTMLはescapeした本文を固定templateへ埋め込みます。cleanは宣言なし、declaredは実encoding、mismatchedは異なる宣言です。ground truthは常に`encoding`で、宣言を正解にしません。
- サイズ制限はHTML全体に適用するため、HTML構文自体やmetaタグが途中で終わることがあります。`complete`が保証するのは文字コード境界でありHTML構文の完結ではありません。元templateの宣言を`declared_encoding`に記録します。

## 現段階の制約

外部corpusの取得、license本文の自動検証、model学習、近重複排除、HTTP metadata、壊れたHTMLの体系的生成は含みません。
v1は書き出し前の検証のためartifactをメモリに保持します。元文書と全variantの合計を1回64 MiBまでに制限し、超過は出力前に拒否します（Python object等のoverheadはこの値に含みません）。大規模corpus投入にはstreaming stagingへの拡張が必要です。
取得・保存全体の予算は実行担当が別途管理します。この基盤のtest成功はdetectorの精度改善を意味しません。
