<!-- SPDX-License-Identifier: MIT -->
# Paris24 ratio感度実験の結果

[事前固定した仕様](RATIO_VARIANT.ja.md)と実装をcommit `fa32d55`に保存してから実行した。
係数未変更baselineのcontent hashは
`d34ffb575ce241519978ff704c9da96c821f67f3cae39dff54cbbde23f6ea9a6`。
各modelは24録音だけで学習し、別のtuning 8録音の全16 encoding入力を評価した。
validationの新たな予測や独立holdoutの開封は行っていない。

## 全条件の結果

cp1252の母数は各8入力。範囲外confidence件数はUTF-8も含む全16入力の全候補で数える。
全条件でUTF-8 exact/decode-equivalentは8/8、両encodingのlanguage一致は各8/8だった。

| model | ratio因子 | cp1252 exact | cp1252 decode-equivalent | 範囲外confidence | 事前基準 |
| --- | ---: | ---: | ---: | ---: | --- |
| identity | 1.00 | 1 | 4 | 0 | 対照 |
| identity | 0.95 | 4 | 7 | 0 | 適格 |
| identity | 0.90 | 8 | 8 | 0 | 次段階候補 |
| identity | 0.80 | 8 | 8 | 1 | 不採択 |
| filtered | 1.00 | 2 | 5 | 0 | 対照 |
| filtered | 0.95 | 5 | 7 | 0 | 適格 |
| filtered | 0.90 | 8 | 8 | 0 | 次段階候補 |
| filtered | 0.80 | 8 | 8 | 2 | 不採択 |

因子1と保存baseline、および各buildの標準targetとlegacy baselineの候補・bit列・done観測は
完全一致した。正解codecの候補内存在件数は今回exact件数と同じだった。
0.80の出力はclampせず保存し、事前に定めた[0,1]条件により不採択とした。

両profileとも0.90が次段階候補だが、profile間の優劣や標準採用は未決定。
この8録音に合わせた選択なので、8/8を未使用dataの汎化精度として公表しない。
次段階では選んだ因子を固定し、未使用data、性能、incremental、confidenceの妥当性、
他言語・encodingへの影響を別途確認する必要がある。
同じtuningを使って候補gridを追加・微調整することはしない。

private report: `archives/v3-corpus/paris24-ratio-sweep-v1.json`。
content hash: `8ebbe3a8e939488bf89aa1fa2c3d6169a494c99e2cf23faf9dc37419f93cd6d6`。
reportは全候補、score、variant、親hash、build provenance、採否を保持する。
同じ検証済みbuildから2回全条件を観測し、report全体のbyte一致を確認した。
標準model・公開API・engineの共通係数は変更していない。
