<!-- SPDX-License-Identifier: MIT -->
# Paris Stories training専用profile

既存の[validation専用pilot](PARIS_STORIES.md)をtrainingへ流用しない。
別recipe/profileで同じ固定revisionのupstream trainだけを取り込む。
tool/test/本文書はMIT。入力本文はCC BY-SA 4.0、生成modelの配布条件は未決定。

## 元データと固定条件

- repository: `UniversalDependencies/UD_French-ParisStories`
- revision: `dec76f7a1731318b033c578d534410b0a3d4ea5c`
- [README](https://github.com/UniversalDependencies/UD_French-ParisStories/blob/dec76f7a1731318b033c578d534410b0a3d4ea5c/README.md)
  は本文を含む会話corpusとCC BY-SA 4.0、contributorsを記載。
- [LICENSE](https://github.com/UniversalDependencies/UD_French-ParisStories/blob/dec76f7a1731318b033c578d534410b0a3d4ea5c/LICENSE.txt)
  をREADMEとともに出力へ保存する。
- `fr_parisstories-ud-train.conllu`: 2,208,034 bytes、SHA-256
  `558c125ecb84f4e16ef8d8871368e24b8c6054446a06da9a5211fc67abb65a1d`
- notices込みの取得対象は3file、計2,214,251 bytes。test・音声・外部URLは取得しない。
- 既存validation manifest hashはrecipeで固定し、metadataだけを取込時に照合する。

## 実際に見つかった分割上の問題

最初のstrict取込では録音ID欠落によって停止した。全1,387文中27文で `sound_url` がなく、
全て `ParisStories_2020_maisonAbondonnee` に属していた。IDを推測せず、recipeに27件の
sentence IDを列挙して隔離する。隔離対象は必ず録音metadataが欠落し、text/tokenが存在する
ことを検証する。未知の欠落を一括skipする機構ではない。

残る1,360文・33録音についても、既存validationと録音IDが一致する1録音38文があった。
そのidentity hashは `3d6643a3c3dc8219b68ff1a45c1d48c35635be5dea1ca7ffd61a17d8c9b0235c`。
この録音全体をtrainingから隔離する。recipeの指定と実際のvalidationとの一致がなければ失敗する。

隔離はraw cacheの削除ではない。元fileを保持し、理由・sentence ID・recording ID等を
ingestion reportへ記録する。既存validationの本文・splitは変更しない。
既知の除外後も、sentence ID・source hash・originのcross-split重複を拒否してから出力する。
encoding変換の成否やdetectorスコアによる文章選別は行わない。

## 再現

```sh
uv run --no-project python corpus/sources/paris_training.py fetch \
  corpus/sources/paris-training.json /disk/paris-training/raw
uv run --no-project python corpus/sources/paris_training.py ingest \
  corpus/sources/paris-training.json /disk/paris-training/raw \
  --validation-manifest /disk/paris-validation/manifest.json \
  --output /disk/paris-training/input
uv run --no-project python corpus/framework.py generate \
  /disk/paris-training/input/config.json /disk/paris-training/generated \
  --failure-policy record-and-continue
uv run --no-project python corpus/overlap.py \
  /disk/paris-training/generated/manifest.json /disk/paris-validation/manifest.json \
  --output /disk/paris-training/overlap.json
```

元のvalidation parserの2 MiB上限は既定値として維持し、trainingだけ明示的に4 MiBを指定する。
full textのUTF-8/cp1252をstrict往復で生成し、変換不能はframeworkに記録させる。
取込先directoryは既存なら拒否する。途中出力を自動削除する処理はない。

## 初回の観測（2026-09-21）

- 採用入力: 32録音、1,322文、UTF-8原文87,681 bytes。
- UTF-8/cp1252の64 variants全て成功、変換不能skipは0。
- 別出力先の取込・生成について全fileのbyte一致を確認。
- training 32 + validation 16 = 48 source、1,128 pairの既存char5近似重複診断は候補0。
- training manifest: `fdd8e32a85cd6c4604929f62d5402f50bfc69b59b81cc3d08b85fe9494998466`
- overlap report: `33f50a11f9dfd879273c781da9c5663611dfbaa07183de62f068349fa5304b22`

近似候補0でも翻訳・部分転載・同一話者や意味内容の独立性は保証しない。
会話という同一domain内のvalidationであり、独立評価を代替しない。
このPRではmodel再生成・検出精度評価・独立holdout予測は行っていない。
本文やmodelをrepositoryへ公開せず、P01の保留作業も再開しない。
