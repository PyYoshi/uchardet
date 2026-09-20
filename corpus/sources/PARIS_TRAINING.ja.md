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

## training / tuningを分ける新しいrevision

係数を調整する場合は既存validationを転用せず、別recipeへ
`"tuning_recordings": 8`を指定する。既知の隔離を適用した後の32録音について、
recording identity SHA-256の昇順の先頭8録音をtuning、残り24録音をtrainingとする。
順位は本文、文字コードへの変換可否、入力長、検出結果には依存しない。
録音内の文を別splitに分けない。少なくとも1録音をtrainingに残す条件を検証する。

新profileは`paris-stories-recording-training-tuning-v1`。
既存recipeにこのfieldがない場合は従来どおり全録音trainingで、旧profileを維持する。
recipe・出力先を新しくし、既存corpus、validation manifest、modelを上書きしない。
reportには録音ごとの割当と`previous_training_models_reusable: false`を記録する。
通常のframeworkで生成した後、既存split/近重複監査を再実行する。

32録音すべてで学習した旧モデルは、新しいtuning録音を既に学習しているため、
新分割での未学習比較には使えない。24録音だけからmodelを再生成する。
この分割は「未読の独立holdoutを確保した」という主張ではない。既存trainingとして
利用済みの資料を、今後の再学習・較正のために分離する手続きである。
話者・意味内容の独立性は録音IDの分離だけでは保証しない。
係数候補や採否基準はtuning予測を見る前に固定し、独立holdoutは引き続き開封しない。

固定recipeは`corpus/sources/paris-training-tuning.json`。上記ingest/generate commandの
recipeと出力先を変更して再現する。外部再取得は不要で、既存の検証済みraw cacheを使える。

初回の実データ検証ではtraining 24録音 / tuning 8録音、UTF-8/cp1252の64 variantsが
全て成功した。別出力先への再取込・再生成は全fileでbyte一致した。
tuningのfull入力は1,625〜3,331 bytesで、4 KiB上限の候補競合評価に収まる。
長さによる録音の再選択は行っていない。

- 新manifest content hash: `1da3f89ee4325d1216e79aefc078def8fb4d8fec3730f3893deef4af0648bd19`
- validationを含む48 source / 1,128 pairの近似重複候補: 0
- overlap report content hash: `b0691327f16ef9447e5b778ba62088adf70877e55175aa0e18fdfda5f1a87434`

この段階では新modelの学習・tuning予測・係数変更はまだ実施していない。
