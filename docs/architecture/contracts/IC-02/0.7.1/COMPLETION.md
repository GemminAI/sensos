# IC-02 0.7.1 — 完了記録

- **記録の日**：2026-11-06
- **状態**：IC-02（MSR の計測と calibration）の契約・スキーマ・見本・Gate の検査・MSR の実装・lock が対応づいた。**契約は草案（0.x）のままで、1.0.0 ではない**。1.0.0 にする条件は、設計書 §2.6 のとおり、実装との照合（済）と Tomo の承認（未）。
- **決定**：D-97（IC-02 を 0.7.1 に上げる 6 項目）。設計書：v0.7.2 ＋差分版 v0.7.3（vault の `日報/202611/20261106/`。sensos には入れない）。
- **対象のコミット**：sensos `feature/contracts-ic02-v071` の `5473c5c`（`contracts/ic00-v1.0.0` の `c82918f` から 4 コミット）、MSR（meaning-space-runtime）`feature/msr-ic02-v071` の `d6b4774`。
- 下の「契約」の表の sha256 は、`tests/contracts/test_ic02_completion.py` が実際のファイルと照合する。契約を変えるときは、版を上げて、この記録を新しい版の記録に置き換える。

## 1. 契約（この版で固定するもの）

| 契約 | 版 | ファイル | sha256 |
|---|---|---|---|
| 計測の payload（`msr.geometry-measurement`） | 0.7.1 | `msr/geometry-measurement.schema.json` | `d9aa7ea59237c4c6f19d33bbac6506ce0983b10ce46a3ee3a94b076b9bd05f6e` |
| calibration の payload（`msr.calibration`） | 0.7.0（スキーマの中身が変わらないため上げない） | `msr/calibration.schema.json` | `7a702f1ff8305ed808885a46b9b200d75380f66fd45276888867ad1eb93d8c72` |
| Blob の参照（IC-00 とは別の契約） | 0.7.0 | `common/blob.schema.json` | `f17c53bba3b8df0b7755717dd02951c20285aaaf0e13eceb4877ed8925d6a952` |
| 系列の定義・単位・値なしの位置・判定の式・親の参照整合の 5 点（規範の文章） | — | `msr/README.md` | `9ee80714e540f77f5e0c41c34e178968a23b283f00d828756fde894ff65c4c0f` |
| 見本：系列（T=1・T=2、δ なし・あり） | — | `msr/vectors/series.json` | `de25c3ddab5c8632a63a8006bf3b0ea8b2ad7a958a2639a5a0dfde964a4f01e9` |
| 見本：親の参照整合 | — | `msr/vectors/calibration-parents.json` | `6ffd5cbc2ab683640d278ea7ca1e3f818508f39cc02785b8f192144d40024035` |
| 見本：Blob の参照 | — | `common/vectors/blob/blob-refs.json` | `29ebd69dc50a8d284c978145df7f03f31d2511d6b0aeb318f80f5ff5de2c5340` |
| 旧 0.7.0 の計測のスキーマ（残す） | 0.7.0 | `msr/archive/0.7.0/geometry-measurement.schema.json` | `ce96a21095fae83603b73eb0933a7605535455eb335c20fdd0882178e8c1339a` |

- 見本の件数：系列 9（受理 4・拒否 5）、親の参照整合 12（受理 2・拒否 10）、Blob 32（受理 8・拒否 24）。
- IC-00 は 1.0.0 で凍結済み（`IC-00/1.0.0/FREEZE.md`、タグ `contracts/ic00-v1.0.0`）。IC-02 はその封筒を使い、凍結の 15 ファイルを変えていない。

## 2. 不変条件の対応（どこで決め、どこで検査し、どこで試験するか）

| 条件 | 契約で決めた場所 | sensos の検査器（`tools/contracts`） | MSR の実装 | MSR の試験 |
|---|---|---|---|---|
| S3 単独の計測に 4 値の判定を付けない | スキーマ（`verdict.state` が null） | スキーマ | `emit.py` | `test_contract_invariants.py`・`test_contract_emission.py` |
| S13 calibration の空間・揃え方が計測と同じ | README §3.3.1 | **未実装（スキーマでは書けない）** | `analyze.py`・`emit.py`（拒否） | `invariants.py`（`test_contract_invariants.py`） |
| S17 `x-common_prefix` の承認 | 設計書 §3.3 | **未実装** | `envelope.py`（`alignment_extensions`） | 同上・`test_contract_emission.py` |
| S18 ペアの入力の一致 | 設計書 §8 | **未実装** | `emit.py`（`emit_pair`） | 同上 |
| S19・S21 calibration の整合 | 設計書 §8 | 親の参照整合として一部（下の 5 点） | `calibration.py`（`_check_contract`） | `test_contract_calibration*.py` |
| S20・S23 calibration の参照と閾値 | 設計書 §8 | **未実装** | `emit.py` | `invariants.py` |
| S34 Blob の `uri` ＝ `blob:sha256:<sha256>` | `common/blob.schema.json`・設計書 §7.1 | `blob.py`（`check_blob`） | `envelope.py`（`Blob.uri`） | `test_contract_vectors.py`（Blob の見本）・`invariants.py` |
| S24・S25 Blob の sha256・長さ | 設計書 §7.1 | `blob.py` | `envelope.py` | 同上 |
| S35 系列の形・名前の集合 | スキーマ（10 系列、`shape [T]`） | `ic02.py`（`check_geometry`） | `emit.py`（`SERIES`） | `test_contract_series.py`・`invariants.py` |
| S36 値なしの位置と宣言（常に宣言） | `msr/README.md` の表 | `ic02.py`・`blob.py` | `emit.py`（`_series_blobs`） | `test_contract_series.py`・`invariants.py` |
| S37 最後の要素 ＝ `metrics` | `msr/README.md`（T=1 の規定を含む） | `ic02.py` | `metrics.py`（変位が無いとき null） | `test_contract_series.py`（T=1・T=2 の見本とバイト列の一致） |
| S38 ペアの判定の再計算 | `msr/README.md`（判定の式） | `ic02.py`（`verdict_state`） | `calibration.py`（`evaluate_shift_quantized`） | `test_contract_calibration.py`・`test_contract_emission.py` |
| S39 知らない版の拒否 | 設計書 §2.6 | `gate.py`（`PAYLOAD_SCHEMAS`） | 受理する版を `emit.py`・`calibration.py` で固定 | `test_contract_lock.py` |
| 親の参照整合（5 点） | `msr/README.md` の節 | `ic02.py`（`check_calibration_parents`） | `calibration.py`（`_check_contract`・`load_calibration`） | `test_contract_calibration_parents.py`（見本 12 件） |

- sensos の Gate（`check_payload`）が今検査するのは、S34・S24/S25・S35〜S39、親の参照整合、payload のスキーマ。**S13・S17・S18・S20・S23 は sensos の検査器にまだ無く**、契約の文章と MSR 側の試験でだけ確かめている。nvs-runtime の Gate を作るときの課題。

## 3. 実装と lock

| 項目 | 内容 |
|---|---|
| MSR の実装 | `src/msr/geometry/`：`wire.py`（厳密な読み込み・量子化・JCS）、`ids.py`（`content_id`・`artifact_id`）、`envelope.py`、`emit.py`（`emit_single`・`emit_pair`）、`calibration.py`、`analyze.py`、`metrics.py`。sensos のコードは import しない |
| MSR の lock | `tests/contract/contract.lock`：source は sensos `5473c5c`（branch `feature/contracts-ic02-v071`）、vendor 17 ファイルの sha256。`tests/contract/vendor/` は sensos の写しで、手で編集しない |
| 試験側の検査器（MSR） | `tests/contract/ic00_gate.py`（IC-00 の `check_envelope` 相当）・`invariants.py`。sensos の `tools/contracts` に依存しない |
| 親の `content_id` | HEKB から取得し、確かめるのは nvs-runtime（Gate）。MSR は HEKB を呼ばない。`load_calibration(…, parent_contents=…)` が受け取る |
| MSR の既知の限界 | 実行時に JSON Schema の検査はしない（依存は numpy のみ）。手書きの検査（欄の集合・型・範囲・S17/S19/S21・親の整合）で代え、完全なスキーマ検査は Gate の責任とする（設計書 §5） |

## 4. 確かめた結果（2026-11-06、最終のコミットで実行し直した）

| 項目 | 結果 |
|---|---|
| MSR の実際の出力（計測 15 種）を `check_envelope`・`check_payload` に通す | 違反 0 件 |
| T=1・T=2 の series の Blob が、`series.json` の受理見本と完全に一致 | 4 通りとも一致 |
| MSR の calibration 3 種（通常・codebook あり・`x-common_prefix`）を `parent_contents` つきで通す | 違反 0 件 |
| 親の参照整合の見本 12 件を、MSR の読み込みと sensos の `check_calibration_parents` で判定 | 食い違い 0 件 |
| lock と vendor（17 ファイル）、IC-00 の凍結 15 ファイル（タグとの差分） | 一致・差分ゼロ |
| sensos `tests/contracts` ／ MSR pytest ／ カバレッジ ／ ruff・mypy ／ sensos の e2e | 317 件通過 ／ 507 件通過 ／ 100% ／ 問題なし ／ 通過 |

## 5. 公開の状況

- sensos の `feature/contracts-ic02-v071`（`5473c5c`）、MSR の `feature/msr-ic02-v071`（`d6b4774`）、sensos のタグ `contracts/ic00-v1.0.0`（`c82918f`）は push 済み。この記録のコミットは、記録を足した時点ではローカルのみ。

## 6. 1.0.0 にする前に残っていること

- Tomo の承認。
- sensos の Gate に S13・S17・S18・S20・S23 の検査を足すか、nvs-runtime の Gate（IC-05）で検査すると決めること。
- IC-04 の `get` が、親の `content_id` を引ける形で成果物を返すこと（v0.7.3 §2.1 の要件。IC-04 の設計で扱う）。
- 二つ目の利用者での Blob の確かめ（設計書 §7.1。Blob は IC-02 とは別の契約で、1.0.0 は別に決める）。
