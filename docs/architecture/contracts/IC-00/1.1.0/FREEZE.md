# IC-00 1.1.0 — 凍結の記録（下書き）

- **状態：未凍結**（独立検証は合格、D-113）。この記録は下書きで、1.1.0 は凍結していない。1.0.0 との後方互換性の確認（Tomo の 11-07 13:24 の判断）は実施済みで、結果は下の「1.0.0 との後方互換性の確認」に記す。独立検証（D-113）とは別のもの。タグは作っていない。
- **決定**：D-107（1.1.0 は Minor。`sensos-connector` と `sensos-inference` を登録）、D-108（登録の規則と規則選択、`sensos-connector` の payload の制限は未実装、独立検証、順序）、D-109（順序の読み替え、契約版の適用範囲は IC-00 だけ）、D-110（未対応の版は `unsupported_contract_version`、版をまたぐ親子は許可）、D-111（B 形の入力・優先順位・符号）、D-116（D-115 の補足。形式に合わない `content_id` と、各欄の読み方の契約）、D-115（D-114 の補足。`lookup_incomplete` の範囲）、D-114（calibration の参照の検査を 3 状態に分ける）、D-113（独立検証の合格、見本 1 件を凍結の対象から除外）、D-112（D-111 の補足。`parent_unknown` は計算した `artifact_id` で判定、①で符号が出たら①だけ、S4・S16・S5 は③、`parent_envelopes` の全項目を②の対象にする）。`OKF/Decisions.md`
- **設計書**：`SensOS 受け渡し契約 設計書 v0.7.2.md`（vault の `日報/202611/20261106/`）。sha256 `f4a865ccf58027c64ed4b9197bc9bd0ebb76fa8f63bd69e1bf7c7a7dd137b911`。設計書の §2.4・S27 に `sensos-connector` はあるが `sensos-inference` は無い（D-101・D-108 (1) が根拠）。設計書の更新は未実施。
- 下の sha256 は `tests/contracts/test_freeze_v110.py` が実際のファイルと照合する。`contract-v110.lock`（`tests/contracts/`）は 1.1.0 のスキーマの lock で、既存の `contract.lock`（1.0.0）とは別。

## 1.0.0 との関係

- 1.0.0 の凍結（`IC-00/1.0.0/FREEZE.md` の 15 ファイルの sha256、見本、id）は 1 バイトも変えていない。`check.py`・`check-envelope.json`・`schemas.py`・`contract.lock`・`test_schemas.py`・`test_vectors.py`・`make_vectors.py` も変えていない。
- 1.0.0 の `check_envelope` は、1.1.0 の封筒を `schema`（`contract.version` の const 違反）で拒否する。その振る舞いも変えていない。

## 1.0.0 との後方互換性の確認（D-113 の独立検証とは別。1.0.0 の見本・ファイルは読むだけで、変えていない）

試験：`tests/contracts/test_ic00_v110_compat.py`（60 件、全件通過。凍結の記録のファイルには入れない）。

| # | 確認 | 件数 | 結果 |
|---|---|---|---|
| 1 | 1.0.0 の `check-envelope.json` 全件（受理 7・拒否 30）を `check_envelope_versioned` に通し、(a) 見本の期待と (b) 1.0.0 の `check_envelope` の出力（受理・拒否と符号の集合）を比べる | 37 | 37 件とも (a)(b) 一致。食い違い 0 |
| 2 | 上の 37 件と 3 の 17 件で `unsupported_contract_version` が出るか | 54 | 0 件 |
| 3 | 1.0.0 の `envelope-ids.json` の 17 件の `content_id`・`artifact_id`・封筒の JCS の sha256 が、記録と一致し、`check_envelope_versioned` の出力が 1.0.0 と同じで、id の不一致の符号が出ないこと（封筒の `contract.version` は 1.0.0 のまま） | 17 | 17 件とも一致。食い違い 0 |
| 4 | 1.1.0 の見本から作った、`contract.version` が 1.0.0 で `sensos-connector`・`sensos-inference` の封筒（observation・interpretation の各 2 件。id は再計算）が、A・1.0.0 の `check_envelope`・B のどれでも S4 だけで拒否されること | 4 | 4 件とも S4 のみ |
| 5 | 1.0.0 の成果物を親にする 1.1.0 の子（A 形・B 形）の受理 | 1 | `parent-1.0.0-child-1.1.0` が A・B とも受理（`parent-versions.json` の 14 件の範囲で、1.0.0 の親・1.1.0 の子で、親の読み替えの誤りでない見本は 1 件。ほかの 13 件は他の組み合わせ・拒否の見本） |

食い違い：なし。確認していないもの：1.0.0 の見本に無い入力（見本の範囲外）、nvs-runtime など他の実装からの利用（Gate は未実装）。この確認で 1.1.0 の記録のファイル（スキーマ・検査器・見本）は変えていないため、sha256 の表は変わらない。

## calibration の参照の検査（D-114、1.1.0 のみ。1.0.0 は変えていない）

- 3 つの状態を分ける：`calibration_unknown`（`calibration_ref.artifact_id` が `lookup` に無い）／`calibration_mismatch`（項目があり `content_id` がそろっていて、`calibration_ref.content_id` と一致しない）／`lookup_incomplete`（項目はあるが `content_id` が無い、または null）。1.0.0 の `check_envelope` は、`content_id` の無い項目を `calibration_mismatch` にする（変えていない）。1.1.0 だけが分ける。`ic00_v110.py` の修正。A 形・B 形とも同じ経路（B 形の親の検査は変えていない）。
- `calibration_ref` が `parents` に含まれなくてよいことを確かめた：IC-00 の封筒の定義（設計書 v0.7.2 の 163・165 行、provenance スキーマ、1.0.0 の `check.py` 107〜116 行）は両者を独立に扱う。含めるよう求める S20（762 行）は IC-02 の計測の payload の規則で、IC-00 の検査器の範囲外。
- 見本の追加（`vectors/check-envelope.json` に 10 件。`parents` は空で `parent_unknown` は並ばない）：`v110-calibration-{null, ok-not-in-parents, unknown-not-in-parents, mismatch, lookup-incomplete}` と、1.0.0 の動作の記録 `v100-calibration-{同じ 5 件}`（`v100-calibration-lookup-incomplete` の期待は `calibration_mismatch`）。既存の 1.1.0 の見本の期待結果は変わらない（既存の見本に `calibration_ref` が非 null のものは無い）。
- **D-115（D-114 の補足）**：1.1.0 の `lookup_incomplete` は、`calibration_ref.artifact_id` の項目が `lookup` にあるが `content_id` が**文字列として存在しない**とき（キーが無い・null・str 以外の型：int・bool・list・dict など）。`content_id` が文字列で `calibration_ref.content_id` と違うときだけ `calibration_mismatch`。実装は `isinstance(content_id, str)` で判定する（bool は str ではない）。1.0.0 は変えていない（どの場合も `calibration_mismatch`）。D-115 による修正前は、null だけが `lookup_incomplete` で、int・bool・list・dict は `calibration_mismatch` だった。
- D-115 の見本の追加（`check-envelope.json` に 10 件。D-116 でさらに 2 件）：`{v110, v100}-calibration-lookup-content-id-{null, int, bool, list, dict}`（1.1.0 の期待は `lookup_incomplete`、1.0.0 の期待は `calibration_mismatch`）。既存の見本の期待結果は変わらない。
- **D-116（D-115 の補足）**：(1) `lookup` の `content_id` が文字列でも、IC-00 の `content_id` の形式に合わないときは `lookup_incomplete`（1.1.0 のみ。1.0.0 は `calibration_mismatch` のまま）。形式は `common/provenance.schema.json:34` の `$defs.contentId` の既存の pattern（`^cnt:[0-9a-f]{64}$`、封筒の `artifact.schema.json:24` と同じ）をそのまま読み込んで使い、新しい規則は作っていない。(2) `lookup` の各欄は、その欄を使う検査の要件に従う（calibration の照合と id の再計算は `content_id`、S5 は `seq`、S8 は親の項目の `observation_id`）。S8 の現行動作を契約として記録した（動作は変えていない）：親の `observation_id` のうち None（キー無し・null）を除いた種類数で判定する。親がすべて null か欠落なら、子が null で受理・非 null で S8。親に非 null の 1 種類があれば、子が同じで受理・null で S8。親に int・空文字があるときは型や形式を検査せず非 null の 1 種類として扱う。`observation_id` の欠けに `lookup_incomplete` は出さない。calibration の項目の `observation_id` は、どの検査も読まない。親封筒そのもの（B 形の `parent_envelopes`）の `observation_id` はスキーマ検証の対象で、キーが無ければ `parent_invalid`。(3)〜(5) は現状の動作がすでに合っている（変更なし）：`calibration_unknown` のとき calibration に依存する S5 の比較は行わず、id の再計算は行う。`lookup_incomplete` のときは不足した欄に依存する比較だけを行わない。B 形は子の `calibration_ref` を `parent_envelopes` から作った `lookup` だけで引き、親の `calibration_ref` は `ancestor_lookup` で引く。(6) 試験は、期待符号に加え、実行された検査と実行されなかった検査も確かめる（`test_ic00_v110.py` の `test_d116_*`。`lookup` を読み取りの記録つきで渡し、改ざんした入力で id の再計算を確かめる外からの観測で、実装の内部は見ていない）。
- D-116 による見本の移動：`{v110, v100}-calibration-lookup-content-id-bad-format` を `check-envelope-unspecified.json` から `check-envelope.json`（凍結の対象）に移した。期待は、1.1.0 が `lookup_incomplete`（D-115 の時点では `calibration_mismatch`）、1.0.0 が `calibration_mismatch`（変わらない）。`check-envelope-unspecified.json` は削除した。
- **決めずに残す点（D-116 (7)。実装は保証しない。凍結の対象外）**：`observation_id` の型・形式の検証を行うか（現状は行わない）／`content_id` 由来と `seq` 由来の `lookup_incomplete` を符号の集合で区別するか（現状は区別しない）／B 形で `parent_envelopes` の親の calibration の項目が不完全なときの扱い（動作は未確認）。追加検証の対象（後続）：欠けた `observation_id` を持つ項目を複数の親に混ぜたときの S8／`observation_id` が bool・list・dict のときの S8。
- B 形の calibration の参照先（D-112 の未規定の点）に依存する見本は、追加していない。
- D-113 の独立検証と、1.0.0 との後方互換性の確認は、D-114・D-115 の修正の前に行ったもの。D-114 (3) により、直した後にやり直す（独立検証の再比較は未実施。互換性の試験 `test_ic00_v110_compat.py` は修正後も通過）。

## 範囲（1.1.0 で足したもの）

| # | 内容 | ファイル |
|---|---|---|
| 1 | 1.1.0 のスキーマ（`$id` は `sensos:contracts/IC-00/artifact/1.1.0`、`contract.version` の const は `1.1.0`。`provenance` は 1.0.0 を `$ref`） | `IC-00/1.1.0/artifact.schema.json` |
| 2 | 1.1.0 の検査器：1.0.0 の一覧に `sensos-connector`・`sensos-inference`（どちらも observation だけ）を足した | `tools/contracts/ic00_v110.py` |
| 3 | `contract.version` だけを読む段（スキーマ検査より前）と規則選択。未対応の版は `unsupported_contract_version`。`contract` が無い・型が違う封筒は `schema`。版をまたぐ親子：A（lookup の保存済み `content_id` を使う）と B（親の封筒を親の版の規則で検査し、`content_id` を親の元の `contract` から再計算する） | `tools/contracts/ic00_versions.py` |
| 4 | 見本：規則選択と producer（`check-envelope.json`）、親子の 4 通りと A・B の違い、D-111・D-112 の優先順位（`parent-versions.json`） | `IC-00/1.1.0/vectors/` |

## 凍結の範囲の外・未実装

- **`sensos-connector` の payload の制限は未実装**（設計書 §2.4「外部の要求の記録と Record で持ち込まれた報告だけ」、S28 以降）。IC-06 の payload スキーマができるまで実装しない（D-108 (3)）。1.1.0 の検査は producer と kind の組だけで、検証済みとは扱わない。
- **凍結の対象から外れた見本（D-113）**：`grandparent-missing-from-ancestor-lookup`（A 形の期待は空、B 形の期待は `parent_invalid`・`parent_unknown`。期待は変えていない）を、`parent-versions.json` から `parent-versions-unspecified.json` に移した。理由：祖父母の `content_id` が無く親の `artifact_id` を計算できない場面で、D-111 (4)（この期待を明示）と D-112（この点に依存する見本は凍結に入れない）の文面が衝突するため。D-111 (4) の 3 件のうち 1 件はこれで凍結の外になる。`parent-versions.json` は 14 件、`parent-versions-unspecified.json` は 1 件。
- **独立検証（D-108 (4)）の合格（D-113）**：独立の検査器との比較で、A 形は 50 件中 50 件、B 形は 15 件中 15 件が一致し、食い違いは 0 件。状態は「未凍結」のままで、凍結（タグ）は別の手順。
- `FREEZE` のタグは作っていない。
- nvs-runtime の Gate は未実装（D-109 (5)(6)）。この検査器は参照実装で、nvs-runtime から使われていない。
- `make_vectors_v110.py`（1.1.0 の見本の生成器）は範囲に入れない（1.0.0 の `make_vectors.py` と同じ扱い）。
- 親子の版の検査（B）の入力・優先順位・符号は D-111・D-112 に従う。
- **B 形で未規定の点（D-112。実装は現状のままで、凍結の対象に入れない）**：(a) 親の `artifact_id` を計算できないときの符号（実装は、その親から `parent_key_mismatch` を出さず、親の親が無いことを `parent_unknown` として出す）、(b) `ancestor_lookup` の項目に欠けがあるときの扱い、(c) 子の `calibration_ref` の参照先を親から作った lookup だけで引くか（実装は親の封筒だけで引く）、(d) 親に対する `calibration_unknown` の判定に `ancestor_lookup` を使うか（実装は使う）。この 4 点に依存する B 形の見本は、`vectors/parent-versions-unspecified.json` に分ける（凍結の対象外）。

## sha256（下書きの記録）

| ファイル | sha256 |
|---|---|
| `docs/architecture/contracts/IC-00/1.1.0/artifact.schema.json` | `d1ba7c8ff80700eb6111a81e0b06e3ba0b9367887be8588a7187fdee9bb9e39e` |
| `tools/contracts/ic00_v110.py` | `4c57ecf098757dfcf491d96a31e42a639b1713652a1a7179d94de72ab5d38ac4` |
| `tools/contracts/ic00_versions.py` | `52c1c6c3278ae71e66992604391a760f6901afe1c41f5cd8a068768e7bf5f268` |
| `docs/architecture/contracts/IC-00/1.1.0/vectors/check-envelope.json` | `448f4943e1f39506e57f7f8590a620162b1f5dfa4625fa6dd60fa26841646ae1` |
| `docs/architecture/contracts/IC-00/1.1.0/vectors/parent-versions.json` | `3fe7296cfdb07a71298f6f74ee4d084c46866e9bf752d9982e54c1941095050d` |

## 変更の規則

1.1.0 の凍結後は、`IC-00/1.0.0/FREEZE.md` の「変更の規則」（設計書 §2.5）と同じ。この下書きの段階では、記録のファイルを変えたら、上の sha256 を更新する。
