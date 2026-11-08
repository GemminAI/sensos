# IC-02 0.9.0 — 先頭 128 行の固定窓（D-129）

- **日**：2026-11-08。**状態**：草案（0.x）。ローカルのみ（push・タグなし）。
- **決定**：D-129（窓を別の成果物として、元の軌跡との対応は `parents`。`common_prefix` で全長を計測する案は採らない）。D-120 の承認の対象にしない。
- **変えたもの**：`msr/geometry-measurement.schema.json` を 0.9.0（`single` に `input_scope`）、`msr/trajectory-window.schema.json` を新規（0.9.0）。`msr/calibration.schema.json` は 0.8.0 のまま。
- **残したもの**：IC-02 0.8.0 の計測のスキーマと README は `msr/archive/0.8.0/` に書き換えずに写した。0.7.1 の計測は旧規則のまま Gate が読む。
- **変えていないもの**：IC-00 1.0.0（凍結の 15 ファイル、`c82918f`）と 1.1.0（`c0064c8` の 5 ファイル）。IC-00 の producer の登録（`nvs-runtime`×`observation` は 1.0.0・1.1.0 とも既に許可）。
- **契約の本文**：`msr/README.md` の「窓」の節。検査器：`tools/contracts/ic02_window.py`。見本：`msr/vectors/window.json`（`tools/contracts/make_vectors_window.py` で生成。期待する符号は手で書き、実装と食い違えば生成を止める）。
- **sha256 の記録**：`tests/contracts/contract-ic02-v090.lock`（`test_ic02_window.py` が照合する）。
- **ベース**：sensos `feature/contracts-ic02-v080` の `bbc085b` ＋ IC-00 1.1.0（`feature/contracts-ic00-v110` の `c0064c8`、ファイルが重ならないのでそのまま merge）。
