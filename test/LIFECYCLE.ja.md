<!-- SPDX-License-Identifier: MIT -->
# 小規模なnative lifecycle比較

`uchardet-lifecycle`は通常の空入力、ASCII、UTF-8、cp1252の小入力について、
fresh detectorとreset再利用の同一feed結果を比較するCTest。
4入力を3巡し、直前の文書とは異なるencodingや空入力へ切り替える。

- finalize後のresetがfreshと同じ初期状態へ戻ること。
- 途中までfeedした文書をresetで破棄した場合もfreshと一致すること。
- 同一feed後、および1回のfinalize後のdoneと候補一覧の一致。
- 候補数・順序・encoding・language（nullと空文字も区別）・confidence bit列を比較。
- finalize後のgetter再読で出力が変わらないこと。

独自のencoding正解をこのtestへ埋め込まず、同一入力のfresh結果を対照にする。
自然文corpusのaccuracy試験やchunk間一致試験を置き換えない。
`uchardet_is_done`は「追加入力が不要」の意味であり、Python wrapperの`closed`と
同じ状態を表すと仮定しない。

```sh
cmake -S . -B /disk/lifecycle-build -DBUILD_TESTING=ON -DBUILD_SHARED_LIBS=OFF
cmake --build /disk/lifecycle-build --target uchardet-lifecycle
ctest --test-dir /disk/lifecycle-build -R '^native-lifecycle$' --output-on-failure
```

CTest timeoutは10秒。標準engineや公開APIを変更しない。
CIではstatic presetに加え、Linux/macOS/WindowsのRelease shared libraryにも
同じtestをリンクして実行する。既存の公開関数`uchardet_is_done`がGNU/Darwinの
export一覧から漏れていた問題を修正し、shared構成のリンク回帰も検出する。
error/OOM注入、arbitrary-byte fuzz、大入力、並列利用、language weightの全契約は未対象。
nativeの繰返しfinalizeやfinalize後feedについては、Python wrapperが呼出しを抑止する
挙動とnative C APIの保証を混同せず、今回のtestで保証を追加しない。
P01を再開したり、#117/#118/#119の全完了を主張したりするものではない。
