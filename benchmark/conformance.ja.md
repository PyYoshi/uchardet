# v3 native conformance 基盤

内部stateの任意観測とBOM境界の原因調査は [introspectionガイド](introspection.ja.md)
を参照してください。

`uchardet-conformance` は公開 C API の結果を JSONL で観測する専用 tool です。
`BUILD_BENCHMARK=ON` で既存 benchmark と一緒に build します。
既存 `uchardet-output` の TSV 形式・呼び出し方は変更しません。

```sh
cmake -S . -B build-conformance -DCMAKE_BUILD_TYPE=Release \
  -DBUILD_SHARED_LIBS=OFF -DBUILD_BINARY=OFF -DBUILD_BENCHMARK=ON
cmake --build build-conformance --parallel
uv run --no-project python -m unittest discover -s benchmark -p test_conformance.py
uv run --no-project python benchmark/conformance.py \
  build-conformance/benchmark/uchardet-conformance > conformance.json
```

## 比較を混同しない

- `--baseline PATH`：同じ入力順・feed schedule・fresh/reuse条件で新旧実装を比較。
  JSON record 全体が一致しなければ `regressions` へ記録し、終了code 1。
  baseline も同じ schema の tool が必要です。旧実装に同じ tool を組み合わせて
  build することで、観測器の変更と engine の変更を分離できます。
- `reset_differences`：毎回生成する detector と、reset して繰り返し使う detector
  を比較。不一致は終了code 1。全fixtureを2巡して直前入力の影響も検査します。
- `chunk_differences`：whole-input と 1／7／64／1024-byte／決定的random chunk
  の最終候補・初期／最終done状態を比較します。既存差分を消さず全件報告します。
  原則として調査用で終了codeを変えません。`--strict-chunks` を指定すると不一致を
  終了code 1 にします。終了code 0 はchunk一致や精度の保証ではありません。

completionの最初の観測位置はchunk境界に依存するため、chunk間比較では除外します。
同一feedの新旧比較では含めます。全観測recordは `observations` に残します。
tool失敗・timeout・不正JSONは処理を中断し、正常な比較結果として扱いません。

## 記録と再現

候補数・配列順・encoding・language・confidenceを記録します。confidenceは
IEEE-754 binary32のbit列を8桁hexで保存し、丸められた表示値で比較しません。
入力一覧にはSHA-256、toolには実行ファイルのSHA-256を記録します。
compiler・flags・source commitは別途buildの記録と組み合わせてください。

入力fixtureは空、NUL、ASCII、UTF-8、BOM、不正sequence、seed固定random bytesです。
外部downloadは不要です。追加ファイルは位置引数で渡せます。
各scheduleのrandom seedは各入力の先頭で固定値に戻し、C++整数演算のみで決定します。
Pythonのfixture生成は同一環境で決定的です。Python版を跨いだ再現はhashも照合してください。

```sh
uv run --no-project python benchmark/conformance.py \
  build-new/benchmark/uchardet-conformance \
  --baseline build-old/benchmark/uchardet-conformance
build-conformance/benchmark/uchardet-conformance reuse random test/ja/utf-8
```

## 現段階の限界

- C APIの `uchardet_is_done()` を観測しますが、内部proberの終了理由はまだ観測しません。
- done後も通常のfeedを継続し、最後にdata_endを1回呼びます。二重data_endや
  data_end後のfeedの契約は、このtestによって定義していません。
- allocation失敗の注入、fuzz、language weightのreset契約は後続の検証対象です。
- synthetic fixtureはconformance向けで、accuracyやperformanceの代表corpusではありません。
- 2026-09-20の開始点に対する自己比較では新旧差分0、reset差分0でしたが、
  chunk差分は18件（2巡を含む）ありました。これは許容リストではなく調査開始点です。

新しい独立実装のtoolとPython testにはMIT SPDXを付けています。
既存engine・modelのライセンスは変更していません。
