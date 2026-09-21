# v3 判定観測tool（初期版）

`uchardet-trace` は内部 C++ class を継承する、開発専用の読み取り観測器です。
公開 C API の追加や detector library 内への hook 挿入はありません。
`BUILD_INTROSPECTION` は既定OFFで、通常buildのhot pathには観測処理を追加しません。
内部symbolを参照するためstatic build専用です。
groupとlanguage detectorのheaderには診断accessor用のfriend宣言のみを追加しています。
accessorの実装・event記録・前回snapshotの保持は診断実行ファイルにだけ存在し、
engineのobject layout・vtable・hot pathや公開C APIは変更しません。

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

`singlebyte_selection`はSBCS groupの既存キャッシュを読み取ります。
`cached_best_index`は`children.singlebyte_group`およびmodel統計のindexと対応し、
未選択ならnull。`active_count`はgroupが保持するactive数です。
`selection_path`はgroupがfoundなら`found_shortcut`、rejectedなら`all_rejected`、
それ以外は`unknown`です。detecting状態のキャッシュはconfidence照会でも名前取得時の
fallbackでも更新され得るため、indexがあるだけで最大scoreによる選択と断定しません。
GetConfidence/GetCharSetNameを追加で呼ばず、engineの計算や状態を変更しません。
SBCS内部の選択とC API全候補の先頭選択も別です。

JSONLの `initial`／`after_feed`／`after_end` eventには次を記録します。

- `input_state`：0=ASCII、1=escape系、2=high-byte入力。
- `start`／`got_data`／`done`：内部flagの実際の値。
- `shortcut_encoding`：shortcutが選んだencoding。なければnull。
- `probers`：最上位multibyte／singlebyte group、Latin1、escapeの状態。
  nullは未生成または破棄済み、detecting／found／rejectedは実際のGetState値です。
- `children`：multibyte／singlebyte group直下のchild一覧。group未生成時はnull。
  各childには安定index、`current`（present／active／state）、直前snapshotの
  `previous`、その差分の`changed`を記録します。初観測のpreviousとchangedはnull。
  raw_reportはsnapshotではないため、previousの更新対象にはなりません。
  activeはgroupが持つ実際のflag、stateはchildの実際のGetState値であり、同義では
  ありません。reject等の根本原因は観測していないため `state_reason="unknown"`。
- `language_detectors`: multibyte group内で生成済みのlanguage detector一覧。
  group未生成時はnull。各slotのprober index、language index、内部state、処理文字総数、
  sequence総数、4分類counter（negative / neutral / probable / positive順）を記録します。
  `model_language`は既存modelの静的なlabelで、予測languageではありません。
  modelを持たないCJK detectorではnullです。未生成slotは一覧に含めません。
  `unlikely`はlanguage detector自身のstateであり、groupによるencoding棄却とは別です。

childのindexは同一source revisionのgroup内で安定しており、revisionを跨ぐmodel追加・
並べ替えで変わる可能性があります。encoding名・language名の代わりにindexを使い、
名前取得に伴う副作用も避けています。出力に入力本文・byte列は含めません。

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

group直下childのstate/active変化とlanguage detectorのstate・累積counterは観測できますが、
byte単位のstate machine遷移、rejectの根本原因、threshold以下の候補、rankingの詳細
理由は未観測です。doneとshortcut・group状態から原因を断定しません。
したがってこれはV3-06の初期基盤であり、introspection全体の完了ではありません。

有効／無効buildで `conformance.py --baseline ...` を実行し、同一feedの出力一致を
確認してください。観測tool自体の繰り返し実行についてもtestで決定性を確認します。

## child観測の限定検証

`test_nested_trace.py` は既存の小fixture（空、ASCII、135-byte日本語UTF-8）のみを
使います。新しい不正入力探索、大入力、BOM改善、fuzz・安全性修正は行いません。

```sh
UCHARDET_TRACE="$PWD/build-trace/benchmark/uchardet-trace" \
  uv run --no-project python -m unittest discover -s benchmark -p test_nested_trace.py
```

`UCHARDET_TRACE_BASELINE` に変更前toolを渡すと、追加children fieldを除く従来の
state・raw Report・confidenceが同じであることも比較します。
`UCHARDET_CONFORMANCE`／`UCHARDET_CONFORMANCE_BASELINE` を指定すると、同一feedの
最終候補をfresh／reuse、whole／1／7／64／1024／固定random chunkで比較します。
比較用環境変数を省略したtestはskipとして表示され、検証済みとは扱いません。

初回検証（GCC 16.2.1／同一Release build directory・flags）では、friend宣言により
再compileされたMBCS group／SBCS group／UniversalDetectorの各object memberが変更前と
byte単位で一致しました。archive自体のmetadata差分は別扱いです。
これは当該buildでの生成コード比較であり、性能向上や全toolchainでの一致の主張では
ありません。既定OFFは維持し、診断tool自体の追加出力・allocationは計測用途から除外します。

## language観測の限定検証（2026-09-21）

追加観測は初期化済みのfieldとmodelの静的labelを読むだけです。
GetLanguage / GetConfidence / GetCandidatesを追加で呼ばず、cacheを更新しません。
CJK側の遅延計算済みlanguage/confidenceも読みません。基底の文字counter等だけを読みます。
観測位置はfeed後・DataEnd後であり、1文字ごとの内部遷移を再現するものではありません。

`test_language_trace.py` は従来と同じ空・ASCII・135-byte日本語UTF-8 fixtureだけを使います。

```sh
UCHARDET_TRACE="$PWD/build-trace/benchmark/uchardet-trace" \
  uv run --no-project python -m unittest discover -s benchmark -p test_language_trace.py
```

`UCHARDET_LANGUAGE_TRACE_BASELINE`へ変更前（childrenあり・language_detectorsなし）の
toolを指定すると、新fieldを除いたsnapshot・raw Report・confidenceの一致も検証します。
比較変数がない場合はその比較をskipと表示します。旧children追加前の比較用変数とは別です。

GCC 16.2.1 / 同じRelease build directory・flagsで、変更前 `664101c` と比較しました。
空・ASCII・日本語のwhole / 1 / 7 / 64 / 1024 feedについて旧観測が一致しました。
同一feedでの最終候補も、既存nested testのfresh/reuse・固定randomを含む6 scheduleで一致。
静的library内の全61 object memberもbyte一致しました。archive自体にはmetadata差があり、
archive hash一致とは主張しません。全compilerでの一致や一般的な性能測定ではありません。

135-byte日本語を7-byte feedした後の例では、39 language slotを観測しました。
French modelは45文字・35 sequence、4分類counterはすべて0でした。
これは低頻度・model外の文字対がsequence総数だけに加算される実装によるもので、
4分類の合計をconfidenceの分母と同一視できないことを示します。
当初testが両者の一致を仮定して失敗したため、sourceと実測に合わせてtestを修正しました。
engineのcounterや判定を修正したわけではありません。

modelを持たないCJK slotは同じ45文字でもsequence総数0でした。
これを「model未対応」「文字を未処理」と解釈しません。state_reasonは引き続きunknownです。
新しいfuzz、大入力、安全性修正、BOM改善、独立holdout評価は行っていません。

## prober内部観測の限定検証（2026-09-21）

snapshotの追加field `prober_evidence` は次の2項目を持ちます。
group未生成ならそれぞれnullです。公開C API・Python APIへの追加ではありません。

- `multibyte_machines`: group内indexとcoding stateの数値。
  0は開始、1はerror、2は確定、それ以外はmodel固有の状態です。
  Big5のindex 5は独自の処理なのでnullです。未対応encodingという意味ではありません。
  feed後の現在値であり、途中の全byteの遷移履歴ではありません。
- `singlebyte_models`: 統計modelを持つchildのindex、静的encoding/language label、
  reverse flag、文字・control・frequent・out・sequence counterと4分類counter。
  Hebrewの名前決定用補助proberは含めません。静的model labelは最終候補の名前と
  同一とは限らず、counterをconfidenceとして再解釈・再計算しません。

friend宣言だけで既存classのfieldを読み、layout・vtable・hot pathを変更しません。
coding state machineの文字長・byte位置は生成直後に未初期化の場合があるため読みません。
GetConfidence / GetLanguage / GetCandidatesも追加で呼びません。
候補の順位やrejectの根本原因は引き続き未確定です。

`test_prober_evidence.py`は既存の空・11-byte ASCII・135-byte日本語fixtureを使います。
`UCHARDET_TRACE`に新tool、`UCHARDET_PROBER_TRACE_BASELINE`に変更前
（language_detectorsあり・prober_evidenceなし）のtoolを指定します。
比較変数がない場合は旧観測との比較がskipになります。

GCC 16.2.1 / 同一Release build directory・flagsでbaseline `a56fd958`と比較し、
whole / 1 / 7 / 64 / 1024 feedで追加fieldを除く全snapshotとraw Reportが一致しました。
既存nested testでfresh/reuse・固定randomを含む6 scheduleの最終候補も一致しました。
静的libraryの全61 object memberはbyte一致しました。archive metadataや
全compilerの生成コード、一般的な性能不変まで主張するものではありません。
診断toolのallocation・出力コストは性能benchmarkに含めません。
