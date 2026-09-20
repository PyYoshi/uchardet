<!-- SPDX-License-Identifier: MIT -->
# 自由ライセンス自然文の小規模取得pilot

[Paris Stories会話corpus](PARIS_STORIES.md)をvalidation専用の別ジャンルとして追加しました。
元本文と注釈の権利を区別し、録音単位の文書・splitを維持します。

tool・test・本文書はMITです。外部本文・許諾文のライセンスとは区別します。
Gitにはrecipeとhashだけを保存し、取得本文や加工本文は同梱しません。

## 採用した資料と権利の根拠

Rust bookの日仏露翻訳を、**技術文書の実データpilot**として採用しました。
各repositoryの固定commitの `LICENSE-MIT`、`LICENSE-APACHE`、`COPYRIGHT` を取得・確認し、MITの選択肢を利用します。COPYRIGHT末尾には明示的な別条件がないcontributionについて同じ条件を適用する説明があります。今回の対象はbook本文であり、COPYRIGHTに列挙された旧Rust配下の第三者libraryではありません。

- [日本語translationのMIT本文](https://github.com/rust-lang-ja/book-ja/blob/5092e5395bf32a65b277c3b1cc1a81ba288c7d46/LICENSE-MIT)
- [フランス語translationのMIT本文](https://github.com/Jimskapt/rust-book-fr/blob/42bfcc8ccea02a1272e5fda936dd593b88361b80/LICENSE-MIT)
- [ロシア語translationのMIT本文](https://github.com/rust-lang-ru/book/blob/05d3ba8d94ab12218100b7726d23730304603bef/LICENSE-MIT)

翻訳先のroot許諾文とCOPYRIGHTもhash固定しています。将来別fileを追加する場合は、そのfileに別条件がないか改めて確認します。再配布する場合は原文のcopyright／許諾文と出典を同伴させる必要があるため、ingest出力の `notices/` に3種類とも保持します。
generated modelのライセンス確定は、このsourceの利用条件確認とは別判断です。

Leipzigはdownload text corpusと他serviceで利用条件が異なる可能性があり、今回確認した公式pageがbot challengeを返したため採用していません。challengeを回避せず、確認可能な上記の資料へ切り替えました。UDHRの移管先repositoryについても、Unicode一般のライセンスを根拠に個別資料の条件を推定していません。

## 再現手順

```sh
uv run --no-project python corpus/sources/acquire.py fetch corpus/sources/rust-book-pilot.json /disk/pilot/raw
uv run --no-project python corpus/sources/acquire.py ingest corpus/sources/rust-book-pilot.json /disk/pilot/raw --output /disk/pilot/ingested
uv run --no-project python corpus/framework.py generate /disk/pilot/ingested/fr-cp1252.json /disk/pilot/generated/fr-cp1252
uv run --no-project python -m unittest discover -s corpus/sources -p 'test_*.py'
```

取得先は固定commitを含むraw.githubusercontent.comだけで、redirectを拒否します。21file合計 **381,359 bytes** を上限付きで取得し、byte長・SHA-256不一致なら失敗します。recipe全体の上限は20 MiB、1fileは1 MiB。再実行時は既存cacheをhash検証し、正しければnetwork取得しません。
2026-09-20の初回確認では、調査用のhash確認と実cache取得に各381,359 bytesを使用しました。GitHub APIによる権利・path調査の通信はこれに含まず、全体でも20 MiB未満の小規模取得です。

ingestは完全offlineです。HTMLコメント内の英語対訳、fenced code、見出し／link定義等を除き、残ったMarkdown段落を利用します。完全なMarkdown parserではなく、inline markupや英語の技術語も残ります。languageは文書の主要言語で、全byteが単一言語という意味ではありません。

UTF-8版に加え、ja=cp932、fr=cp1252、ru=cp1251用の段落集合を生成します。strict往復できない段落は**段落全体を除外**して件数を記録します。文字単位のignore／replaceはしません。これはcodecごとに選択biasを生むので、異なる集合の成績を同一corpusのように比較してはいけません。

各chapterに対して、原本URL／commit／hash、抽出version、実UTF-8 hash、段落除外数、license参照を保存します。抽出後の同一本文にはframeworkで完全入力と64／1024／4096-byte上限のvariantを生成できます。ja/fr/ruと各codec用の6 configを出力します。

## 分割と評価上の制限

chapter単位で、導入=training、getting started=tuning、guessing game=validation、common concepts=独立holdout枠へ固定しました。翻訳やencodingが違ってもoriginを同じchapter識別子にし、全言語で同じsplitを適用します。
独立holdout枠は**未使用の章**という意味で、独立した著者・媒体・domainではありません。同じ本の翻訳なので、一般的な自然言語統計やreal-world Webを代表するcorpusとは扱いません。章数も少なく、とくにtuningは短文です。
取得・抽出時点ではdetectorの予測を参照していません。holdoutの予測はmodel／parameterと評価手順をfreezeした後に初めて開き、結果を見て調整したらtuningへ移し、新しいholdoutを用意します。

初回の6 config生成・framework検証は成功し、計96 sampleを生成しました。legacy版では各言語のvalidation章で1段落ずつstrict往復不可により除外されました。ここで公開しているのは取得・生成の検証結果であり、detector精度やmodel品質の改善結果ではありません。
