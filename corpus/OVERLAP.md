<!-- SPDX-License-Identifier: MIT -->
# source 本文の重複監査（実験用）

`overlap.py` は detector を実行せず、生成前の UTF-8 source 本文だけを比較します。
既存の SHA / origin による split 監査を補完する診断であり、データの自動削除・正規化・再分割は行いません。

```sh
uv run --no-project python corpus/overlap.py /path/to/manifest.json /other/manifest.json
uv run --no-project python -m unittest discover -s corpus -p 'test_overlap.py'
```

比較専用 profile `nfkc-casefold-whitespace-char5-v1` は NFKC → casefold →
連続空白の単一空白化を行います。元データは変更しません。非空の正規化本文一致と、
文字 5-gram 集合の Jaccard 類似度（既定 4/5 以上）を区別して報告します。
5 文字未満は近似比較の根拠にせず、空本文同士も一致として扱いません。
`--output report.json` で保存できます。同じ結果なら再書込せず、異なる既存結果の上書きは拒否します。
句読点は残し、言語をまたぐ比較も行います。閾値は `--threshold 4/5` のように指定できます。

出力には source ID、manifest / source / 正規化本文 hash、split、origin、比較ペア、
集合の交差・和の整数サイズ、Unicode version、tool / framework hash を記録します。
本文・gram 自体は出力しません。ただし hash は匿名化を保証するものではありません。
manifest の指定順に依存せず、同一環境・同一入力で同じ JSON になります。

既知の SHA / origin split 漏洩、改変された本文、重複 manifest はエラーです。
独立 holdout は metadata だけを監査し、本文を開かず skipped として記録します。
生成済み sample 本文は開きません。したがって sample の正当性は別途 framework の
`validate` で検証する必要があります。文字コード違いの sample を独立文書として数えません。
複数 manifest が同じ source を保持する場合は各 source record を残し、一致として報告します。

上限は source record 1,000、manifest 合計 8 MiB、読込 source 合計 8 MiB、
1 source と正規化本文それぞれ 64 KiB です。比較前に gram 総数 × (source 数−1)
が 5,000 万以下か確認し、超過時は部分結果を返さずエラーにします。

結果は `DIAGNOSTIC_NOT_LEAKAGE_CLEARANCE` です。近似一致は確認対象であり、
漏洩の確定ではありません。短い定型文には誤検出があり、翻訳・意味的言い換え・
文書内への部分転載は見逃します。ゼロ件でも split 独立性や corpus 品質を保証しません。
既定閾値を corpus に合わせて最適化したと主張してはいけません。
