# IC-02 0.10.0 — 窓の一般化（位置と長さ、D-132）

- **日**：2026-11-08。**状態**：草案（0.x）。ブランチ `contracts/ic02-v0100-window-rows`（sensos の main `594963a` から）。
- **決定**：D-132（Tomo の方針）。窓の位置 `start` と長さ `length` を契約の項目にする。`rows` を新設し、`prefix_rows` は `start = 0` の特別な場合として残す。窓の位置の候補は契約で狭めない。長さの異なる窓は `equal_only` で比べない（`common_prefix` は採らない、D-120）。
- **変えたもの**：`msr/trajectory-window.schema.json`（0.10.0）、`msr/geometry-measurement.schema.json`（0.10.0）。`msr/calibration.schema.json` は 0.8.0 のまま。Gate（`tools/contracts/ic02_window.py`・`gate.py`・`schemas.py`）が 0.9.0 と 0.10.0 の両方を受け付ける。
- **移したもの（書き換えず `git mv`、sha256 は移す前と同じ）**：0.9.0 の `geometry-measurement.schema.json`・`trajectory-window.schema.json`・`vectors/window.json` と、0.9.0 時点の `msr/README.md`（写し）を `msr/archive/0.9.0/` へ。先例は 0.7.1 → 0.8.0 → 0.9.0。
- **変えていないもの**：IC-00 1.0.0 の凍結 15 ファイルと 1.1.0 の 5 ファイル（sha256 を確認）、`archive/0.8.0/` 以前、`IC-02/0.9.0/CHANGE.md`、`vectors/window.json` の内容（47 件・受理 6）。
- **0.9.0 の既存ファイルのうち、やむを得ず触ったもの**：`tools/contracts/ic02_window.py`（版を見て分岐する形に拡張。0.9.0 の出力は変えない＝0.9.0 の見本 47 件が同じ結果で通る）、`make_vectors_window.py`（出力先を archive へ）、`relock_ic02_v090.py`・`contract-ic02-v090.lock`（パスの更新。`ic02_window.py` は 0.10.0 の lock へ移した）、`test_ic02_window.py`（パスの更新）。
- **契約の本文**：`msr/README.md` の「窓」の節。見本：`msr/vectors/window-rows.json`（確定。各件に `derives_from`）と `msr/vectors/window-rows-undetermined.json`（未規定。凍結しない）。生成：`tools/contracts/make_vectors_window_rows.py`（期待は手書き、食い違えば生成を止める）。
- **sha256 の記録**：`tests/contracts/contract-ic02-v0100.lock`（確定の見本・スキーマ・README・生成器・Gate）、`tests/contracts/contract.lock`（スキーマ。0.9.0 の計測は `archived` へ）。
- **次**：MSR と nvs-runtime の対応は別の PR。
