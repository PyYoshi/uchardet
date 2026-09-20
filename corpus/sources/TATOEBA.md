<!-- SPDX-License-Identifier: MIT -->
# Tatoeba CC0: 小規模snapshotとoffline取り込み

このtool・test・文書は新規MIT実装。取得文はTatoebaのCC0 subsetのみを対象にし、
toolのMITと入力文の `CC0-1.0` は別に扱う。既存Rust book adapterは変更しない。

## 固定する前提

- 初期対象は公式CC0 exportの `fra` / `rus` のみ。任意URLや通常exportは受け付けない。
- 公式URLは週次で更新されるためimmutableとはみなさない。取得したbyteをsnapshotとして固定する。
- 1 snapshot当たり圧縮2 MiB、展開20 MiBを上限とする。追加のネットワーク取得・再試行・redirectは行わない。
- snapshot、展開本文、生成文をGitへ追加しない。作業ディスクのGit管理外directoryへ保存する。
- 全入力は `validation` 固定。training／tuning／independentの指定機能はない。

## 形式契約

2026-09-20に取得した公式CC0の仏語・露語snapshotは、UTF-8、LF区切り、4列のTSVだった。
通常sentence exportの3列形式と混同せず、今回のadapterはこの4列をstrictに検証する。

1. 正の数値sentence ID（重複不可）
2. 言語code（対象の `fra` または `rus` と一致）
3. 原文（空文字不可）
4. 追加export metadata（意味未確定、`export_metadata_raw` としてそのまま保存）

第4列の例は `2019-01-12 19:39:42` だが、作成日・変更日・ライセンス変更日等とは断定しない。
quote除去やbackslash unescape、Unicode正規化を行わない。原文中のliteral `\n` も2文字のまま。
形式を将来変更したexport、CR、別言語、重複ID、UTF-8不正は停止する。
これは確認済みsnapshotに対する契約であり、Tatoebaが将来も同じ形式を保証するという意味ではない。

## Captureとoffline操作

Python 3.11以上の標準ライブラリのみを使用する。下記のpathはGit管理外の作業ディスクを指定する。

```sh
# これだけがネットワーク取得する。新規directoryを必ず指定する。
uv run --no-project python corpus/sources/tatoeba.py capture fra /disk/tatoeba/fra-snapshot-1

# 以降はネットワークを利用しない。
uv run --no-project python corpus/sources/tatoeba.py validate /disk/tatoeba/fra-snapshot-1
uv run --no-project python corpus/sources/tatoeba.py ingest /disk/tatoeba/fra-snapshot-1 /disk/tatoeba/fra-input-1 --limit 200
uv run --no-project python corpus/framework.py generate /disk/tatoeba/fra-input-1/config.json /disk/tatoeba/fra-generated-1 --failure-policy record-and-continue
```

`capture` のURLは公式HTTPS CC0の2 URLのみから決定し、任意URL、redirect、再試行は許可しない。
同じ出力pathを指定するとnetwork取得前に停止する。新しい週の再取得は `capture` を明示的に実行し、別directoryへ保存する。
`validate` / `ingest` はcache不足・破損時も自動取得しない。

snapshotには `archive.tsv.bz2`、`sentences.tsv`、`snapshot.json` を保存する。
metadataは両形式のhash・byte数、UTC取得時刻、公式download URL・説明URL・license URL、
sentence数、capture方法、HTTP Last-Modifiedがあればその未解釈文字列を持つ。
offline検証ではhashと長さの照合だけでなく圧縮byteの再展開が保存本文に一致することも確認する。
1個の完全なbzip2 streamのみを受け入れ、展開は上限付きで行う。
途中のI/O失敗でdirectoryが残った場合は完成snapshot扱いせず、新しい出力先を選んでやり直す。

### 既取得archiveのoffline import

別途公式URLから取得済みなら、二重downloadせずに取り込める。

```sh
uv run --no-project python corpus/sources/tatoeba.py import-cache fra \
  /disk/downloads/fra_sentences_CC0.tsv.bz2 /disk/tatoeba/fra-snapshot-1 \
  --captured-at 2026-09-20T13:18:56Z \
  --sha256 REPLACE_WITH_EXPECTED_COMPRESSED_SHA256
```

`--last-modified` で取得時のHTTP header文字列も記録できる。
importでも上限・hash・形式を確認し、`capture_method: "operator-import"` として区別する。
URL由来・取得時刻はoperatorの申告であり、toolがサーバーへ再照会した情報や署名検証ではない。
直接取得は `capture_method: "direct-https"` である。両者ともmutable URLをimmutableと主張しない。

`ingest` は1〜2000の明示limit（既定200）を許可し、新規directoryに `config.json`、
`ingestion-report.json` とsentence単位のUTF-8本文を保存する。
sourceにはsentence ID、言語、元文hash、snapshot圧縮・展開hash、snapshot時刻、URL、CC0 licenseを残す。
同じsnapshot・limitからのconfigとreportは出力directoryに依存せず同じになる。

## Splitと選択の制約

全sentenceの `origin` を `tatoeba:cc0-pilot` に揃える。
sentence IDは別metadataとsource ID・個別source URLで追跡する。
translation graphや近重複が未確認なので、sentence単位のoriginでは翻訳同士のsplit漏洩を検出できない。
共通originにより、将来別manifestで同じcollectionをtraining等へ移した場合は
corpus frameworkのcross-manifest auditで拒否できる。この保守的な群は文書同一性の主張ではない。
adapterを使わずoriginを書き換えたデータや、Tatoeba外の重複までは検出できない。

数値sentence ID昇順の先頭から、明示limit（既定200）まで選択する。
これは再現可能なpilot選択であり、ランダム・均等・代表性のあるsampleではない。
投稿時期や初期投稿者等の偏りがあり得るため、selection方法と全件数・採用件数をreportへ残す。
意味内容・native予測・legacy codecでの表現可否を選択条件にしない。

選択した原文をUTF-8で保存し、仏語はUTF-8／CP1252、露語はUTF-8／CP1251向けのconfigを作る。
Unicode正規化、文字置換、文字削除、legacy codecで表現不能なsentenceの事前除外はしない。
変換不能・非往復mappingはcorpus frameworkの `record-and-continue` で記録する。
このadapterの成功はmodel学習・精度改善・独立評価を意味しない。

## 参照

- [公式download説明](https://tatoeba.org/en/downloads)
- [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/)

source側の将来の説明・配布条件変更を無条件に承認するものではない。
snapshot metadataのURL/hashは由来の追跡用で、署名や法的真正性の検証ではない。
