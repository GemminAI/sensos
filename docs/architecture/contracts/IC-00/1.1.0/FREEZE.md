# IC-00 1.1.0 — 凍結の記録（下書き）

- **状態：未凍結（独立検証の前）**。この記録は下書きで、1.1.0 は凍結していない。凍結には、D-108 (4) の独立検証（設計書だけから書いた独立の実装が見本と全件一致すること）と、1.0.0 との後方互換性の確認が要る（どちらも未実施）。タグは作っていない。
- **決定**：D-107（1.1.0 は Minor。`sensos-connector` と `sensos-inference` を登録）、D-108（登録の規則と規則選択、`sensos-connector` の payload の制限は未実装、独立検証、順序）、D-109（順序の読み替え、契約版の適用範囲は IC-00 だけ）、D-110（未対応の版は `unsupported_contract_version`、版をまたぐ親子は許可）、D-111（B 形の入力・優先順位・符号）、D-112（D-111 の補足。`parent_unknown` は計算した `artifact_id` で判定、①で符号が出たら①だけ、S4・S16・S5 は③、`parent_envelopes` の全項目を②の対象にする）。`OKF/Decisions.md`
- **設計書**：`SensOS 受け渡し契約 設計書 v0.7.2.md`（vault の `日報/202611/20261106/`）。sha256 `f4a865ccf58027c64ed4b9197bc9bd0ebb76fa8f63bd69e1bf7c7a7dd137b911`。設計書の §2.4・S27 に `sensos-connector` はあるが `sensos-inference` は無い（D-101・D-108 (1) が根拠）。設計書の更新は未実施。
- 下の sha256 は `tests/contracts/test_freeze_v110.py` が実際のファイルと照合する。`contract-v110.lock`（`tests/contracts/`）は 1.1.0 のスキーマの lock で、既存の `contract.lock`（1.0.0）とは別。

## 1.0.0 との関係

- 1.0.0 の凍結（`IC-00/1.0.0/FREEZE.md` の 15 ファイルの sha256、見本、id）は 1 バイトも変えていない。`check.py`・`check-envelope.json`・`schemas.py`・`contract.lock`・`test_schemas.py`・`test_vectors.py`・`make_vectors.py` も変えていない。
- 1.0.0 の `check_envelope` は、1.1.0 の封筒を `schema`（`contract.version` の const 違反）で拒否する。その振る舞いも変えていない。

## 範囲（1.1.0 で足したもの）

| # | 内容 | ファイル |
|---|---|---|
| 1 | 1.1.0 のスキーマ（`$id` は `sensos:contracts/IC-00/artifact/1.1.0`、`contract.version` の const は `1.1.0`。`provenance` は 1.0.0 を `$ref`） | `IC-00/1.1.0/artifact.schema.json` |
| 2 | 1.1.0 の検査器：1.0.0 の一覧に `sensos-connector`・`sensos-inference`（どちらも observation だけ）を足した | `tools/contracts/ic00_v110.py` |
| 3 | `contract.version` だけを読む段（スキーマ検査より前）と規則選択。未対応の版は `unsupported_contract_version`。`contract` が無い・型が違う封筒は `schema`。版をまたぐ親子：A（lookup の保存済み `content_id` を使う）と B（親の封筒を親の版の規則で検査し、`content_id` を親の元の `contract` から再計算する） | `tools/contracts/ic00_versions.py` |
| 4 | 見本：規則選択と producer（`check-envelope.json`）、親子の 4 通りと A・B の違い、D-111・D-112 の優先順位（`parent-versions.json`） | `IC-00/1.1.0/vectors/` |

## 凍結の範囲の外・未実装

- **`sensos-connector` の payload の制限は未実装**（設計書 §2.4「外部の要求の記録と Record で持ち込まれた報告だけ」、S28 以降）。IC-06 の payload スキーマができるまで実装しない（D-108 (3)）。1.1.0 の検査は producer と kind の組だけで、検証済みとは扱わない。
- 独立検証（D-108 (4)）は未実施。`FREEZE` のタグは作っていない。
- nvs-runtime の Gate は未実装（D-109 (5)(6)）。この検査器は参照実装で、nvs-runtime から使われていない。
- `make_vectors_v110.py`（1.1.0 の見本の生成器）は範囲に入れない（1.0.0 の `make_vectors.py` と同じ扱い）。
- 親子の版の検査（B）の入力・優先順位・符号は D-111・D-112 に従う。
- **B 形で未規定の点（D-112。実装は現状のままで、凍結の対象に入れない）**：(a) 親の `artifact_id` を計算できないときの符号（実装は、その親から `parent_key_mismatch` を出さず、親の親が無いことを `parent_unknown` として出す）、(b) `ancestor_lookup` の項目に欠けがあるときの扱い、(c) 子の `calibration_ref` の参照先を親から作った lookup だけで引くか（実装は親の封筒だけで引く）、(d) 親に対する `calibration_unknown` の判定に `ancestor_lookup` を使うか（実装は使う）。この 4 点に依存する B 形の見本は、`vectors/parent-versions-unspecified.json` に分ける（凍結の対象外。現在 0 件）。`parent-versions.json` の見本は、この 4 点に依存しない。

## sha256（下書きの記録）

| ファイル | sha256 |
|---|---|
| `docs/architecture/contracts/IC-00/1.1.0/artifact.schema.json` | `d1ba7c8ff80700eb6111a81e0b06e3ba0b9367887be8588a7187fdee9bb9e39e` |
| `tools/contracts/ic00_v110.py` | `f43bbb595b3771d09f1896587e6b960e500e5a4f303cf3a939a64c99a16907d0` |
| `tools/contracts/ic00_versions.py` | `52c1c6c3278ae71e66992604391a760f6901afe1c41f5cd8a068768e7bf5f268` |
| `docs/architecture/contracts/IC-00/1.1.0/vectors/check-envelope.json` | `fa1a32f89ec7cd44251da0e8ccf69351f38384910be7231253096e3e7bee7293` |
| `docs/architecture/contracts/IC-00/1.1.0/vectors/parent-versions.json` | `182902572a65cd7dc654dffa5e321cf548f207aadb640f1e55e027f0f48fe2fa` |

## 変更の規則

1.1.0 の凍結後は、`IC-00/1.0.0/FREEZE.md` の「変更の規則」（設計書 §2.5）と同じ。この下書きの段階では、記録のファイルを変えたら、上の sha256 を更新する。
