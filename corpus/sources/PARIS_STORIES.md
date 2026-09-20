<!-- SPDX-License-Identifier: MIT -->
# Paris Stories: 会話ジャンルのvalidation pilot

tool/test/本文書はMIT。入力本文・注釈のライセンスとは分離します。
技術文書と例文だけでなく、会話を書き起こした文書でmodelのcoverageを確認するための
小規模pilotです。文字コード検出器や独立holdoutの予測は行いません。

## 固定元と許諾情報

対象は `UniversalDependencies/UD_French-ParisStories` の
`dec76f7a1731318b033c578d534410b0a3d4ea5c`、upstream `dev` のみ。

- [README](https://github.com/UniversalDependencies/UD_French-ParisStories/blob/dec76f7a1731318b033c578d534410b0a3d4ea5c/README.md)
  は収集・書き起こしの由来、contributors、`Includes text: yes`、CC BY-SA 4.0を記載。
- [LICENSE](https://github.com/UniversalDependencies/UD_French-ParisStories/blob/dec76f7a1731318b033c578d534410b0a3d4ea5c/LICENSE.txt)
  はtreebankのCC BY-SA 4.0と許諾本文への参照を記載。
- recipeにこの2文書と `fr_parisstories-ud-dev.conllu` のSHA-256/byte長を固定する。

取得はこの3file、合計1,169,312 bytesに限定し、raw.githubusercontent.comの固定commitを
使います。音声URL、upstream train/test、外部参照先へはアクセスしません。
本文や音声はGitへ同梱せず、ingest先には出典・元README・LICENSEを保持します。
抽出や再encodeによる変更はmetadataへ記録します。生成modelの権利を自動的にMITとは扱いません。

候補のFrench-GSDは[README](https://github.com/UniversalDependencies/UD_French-GSD/blob/master/README.md)
で注釈と元本文の権利を区別しているため、同じCC BY-SAという表示だけを理由に本文を
今回の自由ライセンスcorpusへ取り込んでいません。

## 再現

```sh
uv run --no-project python corpus/sources/paris_stories.py fetch \
  corpus/sources/paris-stories.json /disk/paris/raw
uv run --no-project python corpus/sources/paris_stories.py ingest \
  corpus/sources/paris-stories.json /disk/paris/raw --output /disk/paris/input
uv run --no-project python corpus/framework.py generate \
  /disk/paris/input/config.json /disk/paris/generated --failure-policy record-and-continue
uv run --no-project python -m unittest discover -s corpus/sources -p 'test_*.py'
```

fetchはcacheをhash検証し、再実行時はnetwork取得しません。ingestは完全offlineで、
既存output directoryを上書きしません。新しい出力先で再生成して比較できます。
途中に残ったdirectoryを自動削除・再利用するtransactionではありません。

## 文書とsplit

CoNLL-Uの `# text` をそのまま採用し、tokenから本文を再構築しません。
同じ `sound_url` のsentenceを元file内の順に改行で結合し、1録音を1文書とします。
URLはhash化してoriginとするだけで、音声を取得しません。sentence IDは保存します。
語尾の `bis` やUnicode文書名を勝手に正規化・並べ替えません。
形態統語注釈の正当性を検証するtoolではなく、10列形式と必要metadataだけを確認します。

出力はすべてvalidation。upstreamのdevというラベルを自分たちのtrainingへ流用せず、
録音内の文を異なるsplitへ分けません。ただし話者の同一性や録音間の意味的依存を
確認したわけではなく、「16人の独立した話者」「独立評価corpus」とは呼びません。
元READMEの概算件数を転記せず、固定fileの実際のmetadataから文書・文数を集計します。

UTF-8 / cp1252、全体 / 64 / 1024 / 4096 bytesのplain-text variantを生成します。
文字のignore/replaceやcp1252向けの文・段落削除はしません。strict往復不可なら
frameworkがvariant単位のskipを記録します。会話の書き起こしは実HTMLやWeb頻度の代理ではありません。

初回実測: 692文、16録音文書、抽出UTF-8 41,876 bytes。128 variant全て生成成功。
raw cache再検証時の追加取得は0 bytes。native検出・training・独立holdout予測は0件です。
