<!-- SPDX-License-Identifier: MIT -->
# 単一モデル reuse の allocation call-site 観測

64-bit Linux、GNU-compatible linker、Itanium C++ ABI向けの実験tool。
engineや既存modelを変更せず、静的libraryへリンクする診断実行ファイルだけをinstrumentする。
counterはこのsingle-thread tool専用であり、並列測定やthread-safeな汎用allocator監視には使わない。

```sh
uv run --no-project python models/experimental/model_allocations.py \
  identity-training.json filtered-training.json corpus/manifest.json \
  build/src/libuchardet.a allocation-report.json
```

同じfrozen trainingとvalidation/tuning corpusを用いる。独立holdoutを含むmanifestは拒否する。
legacy/identity/filteredそれぞれで通常版と計測版をbuildし、最終snapshot/reset結果を照合する。
128回のwarm-up後、1回のreset/filter/feed/confidenceについて呼び出し回数を記録する。
input/scratch/prober確保、入出力、JSON生成は区間外。時間計測との併用は拒否する。

計測対象はlinker `--wrap`で捕捉できるmalloc/calloc/realloc/freeと、throwing・unalignedの
scalar/array new/deleteの呼び出し。起動時に全8経路を実際に呼び、期待回数との一致を確認する。
計測の自己検証に失敗した場合、0回として成功を報告しない。

**物理的なallocation数、確保byte数、peak/live memoryの測定ではない。**
shared library内部の呼び出し、aligned/nothrow/sized/custom allocator、mmapは捕捉しない。
libraryのLTOや独自allocatorは想定しない。全detectorのallocation gateを満たす証拠にもならない。
0回という結果は、選択した入力と区間の対象call-siteだけに限定する。
API呼び出しの入れ子を物理allocationとして合算しない。各counterを個別に保持する。

compiler/flags、static library、診断source、generated header、実行fileのhashを保存する。
生成modelを公開せず、計測結果を理由に既定modelへ採用しない。
