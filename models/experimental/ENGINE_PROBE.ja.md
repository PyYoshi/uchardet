<!-- SPDX-License-Identifier: MIT -->
# 生成Frenchモデルを候補群へ接続する非デフォルトtarget

単一proberの内部スコアだけでは候補競合の結果を評価できないため、French cp1252の
1 slotだけを差し替えた別static libraryと候補観測実行fileをbuildする。
標準`libuchardet`・CLI・install・Python wheelのmodelを置き換える機能ではない。
通常のCMake設定では実験target自体が存在せず、明示した場合も`ALL`/installから除外する。

## 範囲

- `nsSBCSGroupProber`の`Windows_1252FrenchModel`参照だけを実験target内で置き換える。
- 同じgroupのISO-8859-1/15 French、他言語、UTF-8のlanguage model、ranking処理は維持する。
- したがってFrenchモデル全体の置換ではなく、1 slotのみ異なるhybrid engineの比較になる。
- 出力は既存conformance toolの候補数・順序・encoding・language・confidence bit列とdone観測。
- modelのencoding名が`cp1252`なら、その表記も出力差になる。exact名とcodec互換性を分ける。
- 評価入口は4 KiB以下、既定はone-shot/fresh。Python側と実験実行file側で上限を確認する。
- 大入力の停止調査、追加fuzz、P01依存のBOM試作を再開しない。

## Build

driverは現在Linuxのみ。CMake/C++ compiler以外の新しいdependencyは不要。

```sh
uv run --no-project python models/experimental/engine_probe.py \
  --reference /disk/engine-reference
uv run --no-project python models/experimental/engine_probe.py \
  --training /disk/frozen-training.json /disk/engine-generated
```

`--training`は既存identity/filtered training artifactを、そのhash・依存revision・runtimeを含め
検証してからheaderへ変換する。言語fr、codec cp1252以外は拒否する。
`--reference`はlegacy tableをコピーせず同じmodelへの参照を接続し、adapterだけで結果が
変わらないことを検査する対照。任意の既存出力directoryは上書きしない。

driverは標準buildで実験実行fileが生成されないことを確認した後、明示targetをbuildする。
両方の実行fileとheader、compiler/CMake情報、compile設定、source hashを記録する。
生model/headerは私的build artifactとして扱い、repositoryへ追加しない。

CMakeを直接使う場合は`BUILD_SHARED_LIBS=OFF`、`BUILD_BENCHMARK=ON`、
`UCHARDET_EXPERIMENTAL_MODEL_HEADER=/absolute/path/model.hpp`を明示し、
`uchardet-conformance-experimental`を指定してbuildする。
この低レベル経路は信頼済みC++ header用で、JSON検証を代行しない。

## 比較時の注意

`engine_probe.observe(binary, data, chunk=0)`は4 KiBを超える入力を実行前に拒否し、
各processの実行を10秒で打ち切る。timeoutを正解率・一致として数えない。
標準conformance実行file自体にはこの専用上限がないため、pilotでは必ずこの入口を使う。

trainingと評価dataの重複監査・manifest検証は評価driver側で行う。
低レベルbuild/observe helperを使っただけでcorpus独立性が保証されるわけではない。
モデルの較正・encoding accuracy・性能・権利のgateも別であり、接続成功は採用承認ではない。

CIは明示環境変数`UCHARDET_ENGINE_EXPERIMENT=1`でreference一致と人工modelの結果変化、
標準target不変、default build/installからの分離、入力上限を検証する。
人工modelはこのtestで作った小tableで、自然言語modelの品質を示さない。

## Paired corpus評価

```sh
uv run --no-project python models/experimental/engine_comparison.py \
  /disk/identity-training.json /disk/filtered-training.json \
  /disk/validation/manifest.json \
  /disk/engine-identity /disk/engine-filtered /disk/comparison.json
```

既存paired control validatorでtrainingとの重複、manifest、同一Unicode文書の
full cp1252/UTF-8対を検証する。全入力が4 KiB以下でなければ評価全体を拒否し、
切り詰めたり大きな文書だけを集計から外したりしない。
固定training contractとbuild header・source・実行fileのhashを照合し、
両buildの標準target出力が一致しなければ結果を生成しない。

結果には候補一覧とconfidence bit列を保持する。集計ではcodec aliasを正規化した
先頭候補のexact codec、strict decode後の文字列一致、language一致、正解codecの
候補内存在を分離する。decode-equivalentはその入力だけの性質であり、encoding全体の
互換性・superset関係を意味しない。compatible/superset指標は未評価と明記する。
候補内に正解がないことだけでmodel欠落と断定せず、group内部の選抜も考慮する。
legacy modelのtraining overlapは不明であり、現行生成modelとの公平な独立学習比較を
保証するものではない。
