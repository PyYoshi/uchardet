<!-- SPDX-License-Identifier: MIT -->
# Python-only SequenceModel training profile v1

これは既存のmodel生成試作を精緻化する**未較正の生成仕様**です。
新しいdetector実装ではありません。nativeのcompile／実行、engine登録、既存model置換、
旧table・generator・filterの流用は行いません。P01で保留された作業を再開するものでも
ありません。tool・testは独立したMIT実装であり、生成modelの権利とは別です。

## 実行と成果物

```sh
uv run --no-project python -m unittest discover -s models/experimental -p test_sequence_training.py
uv run --no-project python models/experimental/sequence_training.py train /disk/corpus/manifest.json fr /disk/training.json
uv run --no-project python models/experimental/sequence_training.py validate /disk/training.json
uv run --no-project python models/experimental/sequence_training.py validate /disk/training.json --manifest /disk/corpus/manifest.json
```

testsは人工fixtureとPython subprocessのみです。既存の`test_*.py`全体にはnative
compile/runを行うtestもあるため、この作業の検証commandは上記の限定patternを使います。

出力はprofile/spec、runtime version、生成コード依存hash、文書別整数counts、生成された
SequenceModel契約、audit値、canonical content hashを持つJSONです。native用emitterや
登録機能は追加しません。生成契約は既存の`sequence_contract.validate`で検査します。
同じartifactの再出力はmtimeを変えず、異なる内容への上書きを拒否します。

## training選択

corpus frameworkによるmanifest・source・sample本文の検証を先に行い、指定languageの
trainingから、cp1252・text・complete・byte_limit=nullだけを選びます。
HTML／サイズ制限／切断variantや他splitは数えません。完全版がなければ生成拒否します。
同じsource hash／originの二重投入を拒否し、文書間のpairは生成しません。

各文書について256 symbol countsと疎なbyte pair countsを保存します。これらは実際の
cp1252 sampleから数えた値であり、sample hash・encoder/version・source metadataも
保持します。選択後の文書はsource id順です。集計tableは文書の列挙順に依存しません。
ただし元manifest自体を変更すればcorpus hashも変わるため、artifact全体まで同じとは
主張しません。

## 固定profile

profile名は`cp1252-identity-sequence-training-v1`です。

| 項目 | v1の仕様 |
| --- | --- |
| filter | `identity-unfiltered-v1`。byteを削除・結合しない |
| 正規化 | なし。大小文字は別。Unicode分類versionを記録 |
| 文字分類 | cp1252未定義=255、CR/LF=252、その他Unicode Cc=254、ASCII 0〜9=251、Unicode L*はletter、それ以外=253 |
| 頻出文字 | 観測されたletterを頻度降順、同数はbyte昇順。先頭最大64文字をorder 0〜K−1へ |
| その他letter | order K。これはmatrix外の低頻度文字。予約値250は使用しない |
| pair | 文書内で直接隣接するbyte。特殊分類は頻出文字matrixの対象外 |
| 未観測pair | category 0 |
| 観測pair | 以下の累積massによるcategory 3／2／1 |
| ratio | category 3の出現mass／全letter隣接pairのmass（低頻度letterのpairも分母に含む） |
| keep_english_letters | true。ただし既存engineのfilter切替を保証しない |
| deployment_status | `NOT_ENGINE_CALIBRATED` |
| generated_model_license | `UNDETERMINED` |

頻出文字pairを出現数の降順で並べ、同頻度のpairは一つのgroupにします。
そのgroupより前の累積massが、全頻出文字pair massの95%未満ならcategory 3、
99%未満ならcategory 2、それ以外ならcategory 1です。
比較は整数積で行い、同頻度groupを閾値の途中で分割しません。
そのためpositiveの実際のmassが95%を超えることがあります。
全categoryが必ず出現するわけではありません。

**95%／99%は未較正の初期実験値です。** 未観測pairをnegative category 0とすることも
独立評価が必要な仮定です。これらを変える場合はprofile versionを変更します。
文字・頻出文字pair・positive massがない場合は生成拒否し、架空のratioを補いません。

## ratioと再計算audit

整数のpositive_pair_mass／letter_pair_mass／frequent_pair_massを保存します。
ratioは正確な有理数からbinary32へnearest/ties-to-evenで丸めます。
途中でbinary64除算を挟まないため、二重丸めを避けます。ゼロへunderflowした場合は拒否。
この丸め規則は機構の再現性のためであり、confidenceの適切さを示すものではありません。

通常のvalidateは文書別countsの次元・範囲・pair合計・周辺頻度と文書境界を検査し、
table／ratio／auditを再計算して一致を要求します。metadataだけから元の文章の真正性や
countsの正しさを証明することはできません。
周辺頻度等の条件だけでは、そのcountsを持つbyte順序が実際に存在することも証明しません。
`--manifest`を指定するとcorpus本文を再検証してtrainingをやり直し、artifact全体の一致を
確認します。これは出典の許諾そのものを審査する機能ではありません。

generator自身、model helper、SequenceModel契約、corpus framework、標準libraryの
cp1252 codec sourceを依存hashへ含め、そのcanonical hashを契約のgenerator source hash
に使います。Python version・implementation・Unicode versionも固定します。
別revisionのcodeや別runtimeで検証すると拒否するため、再現時は記録した環境が必要です。

## まだ保証しないこと

- 既存SBCS filter後の分布とtraining分布の一致。
- candidate順位、encoding／language精度、confidence calibration。
- chunking、性能、既存native modelと同等以上の品質。
- 生成データの配布許諾。

自然文生成modelは同梱・公開しません。今回の合格条件は人工fixture上での決定的な生成・
再計算・契約適合であり、品質評価・native接続・採用判断は別gateに残します。
