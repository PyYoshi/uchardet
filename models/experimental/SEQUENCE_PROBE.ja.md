<!-- SPDX-License-Identifier: MIT -->
# 非デフォルトの native SequenceModel probe

`sequence_probe.py` / `sequence-probe.cpp` は、明示契約から生成したモデルを
実際の `nsSingleByteCharSetProber` に渡す診断用harness。
通常のdetectorに登録せず、libraryのsource/既定model/公開APIを変更しない。
filterやprober処理の再実装ではなく、既存static libraryの関数を呼ぶ。

## 実行

```sh
cmake --preset release
cmake --build --preset release --parallel 2
uv run --no-project python models/experimental/sequence_probe.py \
  /disk/contract.json build/release/src/libuchardet.a /disk/sample.bin /disk/probe.json
```

入力のcontractはtraining artifact全体ではなく、その`contract`フィールド。
既存SequenceModel validatorとemitterで検証したheaderを一時directoryに生成し、
trustedなstatic libraryへリンクする。GCC/Clang系driverのC++11 CLIを対象とする。
`--cxx clang++`で切替可能。MSVC driver用のbuild機構は未実装。
`clang++`をsymlink実体の`clang`名で起動してlink条件を変えない。

CLIの一時build/inputは最大64 KiBの入力を扱うための小規模診断用。
compile timeoutは60秒、実行は10秒。自然文生成modelを含むheader/binaryを公開・配布しない。
Pythonから複数文書を扱う場合は、fresh directoryで`build()`を一度実行し、
返されたbinaryに対して`observe(binary, bytes)`を文書ごとに呼べる。
既存binaryの上書きは拒否する。reportの保存には排他的・べき等helperを使う。

## 観測範囲

- 一文書を一回 `FilterWithoutEnglishLettersToBuffer` に通す。
- filterが空ならproberへfeedしない。非空なら一回だけfeedする。
- 単一model、non-reversed、補助name proberなし。
- `state`（0 detecting / 1 found / 2 rejected）、処理文字数、頻出/低頻度/制御文字数、
  sequence総数、4カテゴリcounter、最後のorderを取得する。
- confidenceはbinary32 bitをhex文字列として保存する。内部値は負値や1超にもなり得る。
  確率・公開C APIの最終confidence・較正済みscoreとして表示しない。
- 同じinstanceをresetした後のcounter/state/confidenceも記録する。

観測用subclassからprotected counterを読むだけで、演算・threshold・state遷移を変更しない。
実装は独立したMIT wrapper、呼び出すlibraryと生成modelの権利は別。
新規fileのMITをlibraryやmodelの再ライセンスと扱わない。

## 再現情報と限界

reportは入力/contract/header/library/compiler/binaryのhash、driver名/version、flags、
wrapper/emitterおよびnative headerのhashを持つ。
static libraryが申告したsource revisionから作られたことまで自動証明するものではない。
compiler内部の実行program・標準library・OSを全て固定するbuild manifestでもない。
build directory/環境が変わるとbinary hashが変わり得るため、観測値の一致とbinaryの一致は
別々に確認する。生成物を勝手に同一視しない。

このCLIはraw bytesとcontractの低水準診断であり、corpusのsplit/leakage監査は行わない。
自然文評価では呼出し側がtraining artifact/corpusを検証し、tuning/validationだけを選択する。
独立holdout、全detectorの候補競合、incremental feed、性能、fuzz、安全性網羅を検証しない。
P01の調査を再開するための代替toolではない。

## テスト

```sh
UCHARDET_STATIC_LIBRARY=build/release/src/libuchardet.a \
  uv run --no-project python -m unittest discover -s models/experimental -p 'test_sequence_probe.py'
```

人工モデルでcategory0〜3、低頻度letterのnegative加算、空filter、reset、
1024 sequenceのshortcut境界を検証する。native library未指定ならnative5件はskip。
CIはLinux diagnosticsで実行する。他OSで実行したとは主張しない。
