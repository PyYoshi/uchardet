<!-- SPDX-License-Identifier: MIT -->
# 近似重複候補のグループ診断

`groups.py` は [overlap 監査](OVERLAP.md)を実行し、その候補ペアを辺とした無向グラフの
連結成分を報告します。元データの削除・選択・split変更・model評価は行いません。
独立 holdout 本文は引き続き開かず、元監査の件数・byte・比較量の上限を継承します。

```sh
uv run --no-project python corpus/groups.py /disk/fra/manifest.json /disk/rus/manifest.json \
  --output /disk/groups.json
uv run --no-project python -m unittest discover -s corpus -p 'test_*.py'
```

各 source record はちょうど1つの成分に属します。孤立文も size=1 の成分です。
出力は元監査の hash、source metadata、成分の members、候補辺数、言語、split、
サイズ分布を保持します。成分 ID は決定的に並べた元 source record の最小 index。
同じ結果の保存は書き直さず、異なる既存結果の上書きは拒否します。

`illustrative_member_weight=1/size` は、成分ごとの総重みを1とする場合の診断例です。
既存 benchmark の集計には適用しません。source数から成分数への減少を確認することで、
似た例文の多さが集計を支配し得るか検討できますが、統計的な有効標本数ではありません。

重要な制約:

- A≈B、B≈C でも A≈C とは限らない。連結成分は相互同一な文の集合ではない。
- 大きい成分は定型文や鎖状の類似関係でも生じる。自動削除や代表文選択に使わない。
- 別成分でも翻訳・意味・同一著者による依存は残る。成分単位で split しても独立性は保証しない。
- hash / origin の既知 split 漏洩は元監査で拒否される。新たな cross-split 成分は
  正規化一致・近似候補の要確認箇所であり、漏洩確定ではない。
- 閾値の変更は分析方針の変更として記録する。validation に合わせて最適化したものを
  未使用 holdout の結果として扱わない。

出力状態は `REVIEW_GROUPS_NOT_INDEPENDENT_SAMPLES`。候補の人手確認や将来の
重み付け比較を準備するための情報であり、現在のaccuracyスコアを書き換えるものではありません。
