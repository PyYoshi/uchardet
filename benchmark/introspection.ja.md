# v3 判定観測tool（初期版）

`uchardet-trace` は内部 C++ class を継承する、開発専用の読み取り観測器です。
公開 C API の追加や detector library 内への hook 挿入はありません。
`BUILD_INTROSPECTION` は既定OFFで、通常buildのhot pathには観測処理を追加しません。
内部symbolを参照するためstatic build専用です。

```sh
cmake -S . -B build-trace -DCMAKE_BUILD_TYPE=Release \
  -DBUILD_SHARED_LIBS=OFF -DBUILD_BINARY=OFF \
  -DBUILD_BENCHMARK=ON -DBUILD_INTROSPECTION=ON
cmake --build build-trace --parallel
build-trace/benchmark/uchardet-trace 7 test/ja/utf-8
UCHARDET_TRACE="$PWD/build-trace/benchmark/uchardet-trace" \
  uv run --no-project python -m unittest discover -s benchmark -p 'test_*.py'
```

診断入力は64 KiB以内に制限します。超過はエラーであり、黙って切り詰めません。
chunkは0（全体）、1、7、64、1024を指定できます。性能測定には使いません。

## 観測できること

JSONLの `initial`／`after_feed`／`after_end` eventには次を記録します。

- `input_state`：0=ASCII、1=escape系、2=high-byte入力。
- `start`／`got_data`／`done`：内部flagの実際の値。
- `shortcut_encoding`：shortcutが選んだencoding。なければnull。
- `probers`：最上位multibyte／singlebyte group、Latin1、escapeの状態。
  nullは未生成または破棄済み、detecting／found／rejectedは実際のGetState値です。

`raw_report` はengineのReport callbackをそのまま記録します。
confidenceはbinary32 bit列です。**これはC APIの最終候補順位ではありません。**
C API wrapperによる重複処理・confidence順への挿入・language weight適用の前です。
最終候補は同じ入力とchunkで `uchardet-conformance` を併用して確認します。

追加のGetConfidenceやGetCandidatesは呼びません。これらは内部の計算状態を変える
可能性があるため、観測のために計算を追加して判定へ影響させることを避けます。

## BOM chunk不一致の最小例

現実装の境界挙動を固定した再現testを `test_trace.py` に含めています。
これは望ましい仕様の定義ではなく、改善前の診断用testです。

| bytes | feed | 観測 |
|---|---|---|
| EF BB BF | 3 bytes一括 | UTF-8 shortcut、done=true |
| EF BB BF | 1 byteずつ | 最初のfeedでstart=false、BOM shortcutなし |
| FF FE | 2 bytes一括 | BOM shortcutなし |
| FF FE 00 | 3 bytes一括 | UTF-16 shortcut |

原因は `nsUniversalDetector::HandleData` の冒頭にあります。
最初の呼び出しで `mStart=false` とし、`aLen>2` の場合のみBOMを調べます。
prefixを次のfeedへ保持しないため、1-byteずつ渡すとBOM判定へ戻りません。
UTF-16の2-byte BOM単独も同じ長さ条件により検出されません。
この変更では修正していません。bufferingやEOF処理を導入する場合は、候補・doneの
変更を意図的な別実験として検証します。

## 未観測の領域

group内部の個々のprober、内部state machineの遷移、reject理由、threshold以下の
候補、rankingの詳細理由は未観測です。doneとshortcut・group状態から推定できても、
JSONには原因を断定する架空のreason fieldを追加しません。
したがってこれはV3-06の初期基盤であり、introspection全体の完了ではありません。

有効／無効buildで `conformance.py --baseline ...` を実行し、同一feedの出力一致を
確認してください。観測tool自体の繰り返し実行についてもtestで決定性を確認します。
