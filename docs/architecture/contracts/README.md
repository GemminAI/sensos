# SensOS 受け渡し契約（Contracts）

**正の設計書**：`~/vaults/20260124/日報/202611/20261105/SensOS 受け渡し契約 設計書 v0.6.2.md`（v0.6.2、ai-draft、Tomo の承認待ち）。
この README はその要約で、食い違いがあれば設計書が正。`msr/` の 2 つのスキーマは、同じフォルダの
`geometry-measurement.schema.json`（0.6.2）・`calibration.schema.json`（0.6.1）をそのまま写したもの（中身を変えない）。

## 0. 目的と原則（§0・§0.1）

目的：MM が意味を同定し、MSR が幾何を測り、CLE が構造の整合を検査し、HEKB が経験を保ち、nvs-runtime が統合する一連の処理について、
後から「何を観測し、何を測り、何を解釈し、何を根拠に判断したか」を再構成できること。

1. 契約が先、実装は後。部品は他の部品の内部実装を知らず、コードを import しない。
2. 部品は部品を直接呼ばない。成果物は nvs-runtime に返し、nvs-runtime が出所と順序を付けて HEKB に置く。相手の成果物は nvs-runtime が `artifact_id` で渡したときだけ参照する（H7）。
3. 種類は D-70 の 5 種類（Observation／Evidence／Interpretation／Selection／Outcome）。計測値・解釈・検査は Interpretation。人の決裁は Selection（HANKO）だけ。Evidence は HEXT だけ。
4. 書き換えない、合算しない（H1・H3・H4）。
5. 契約は事実・測定・解釈の境界を保証する。JSON Schema で書けない約束は意味の不変条件（S1〜S25）にして試験にする。

## 1. 置き場所と版の管理（§1）

```
docs/architecture/contracts/
├── README.md
├── common/  artifact.schema.json  provenance.schema.json  uncertainty.schema.json  vectors/
└── msr/     geometry-measurement.schema.json  calibration.schema.json
```

- 版：契約ごとに `contract_id`（例 `IC-00`）と Semantic Versioning。互換を壊す変更は major を上げる。
- 各部品のリポジトリは `tests/contract/contract.lock` に `contract_id`・版・sensos のコミット・スキーマのパス・sha256 を記録し、CI で一致を確かめる。不一致なら落ちる。契約の変更は sensos での明示の更新とレビューを経てから、各部品が lock を更新する。
- このリポジトリの lock：`tests/contracts/contract.lock`。
- 参照実装：`tools/contracts/`（標準ライブラリと jsonschema だけ）。**言語に依らない定義は `common/vectors/` の見本**で、将来の Rust 版は見本だけで同じ結果を確かめる（`vectors/README.md`）。

## 2. IC-00 の封筒（要約。正は `common/artifact.schema.json`）

`contract{id,version}`・`content_id`・`artifact_id`・`kind`・`payload_schema`・`payload`・`producer{name,version,build}`・`session_id`・`observation_id`・
`event_span`・`space_id`・`parents[{role,ordered,artifact_ids}]`・`policy_refs`・`calibration_ref`・`rule_refs`・`observed_at`・`seq`・`produced_at`・`extensions`（キーは `x-`）。

- `content_id = "cnt:" + sha256(JCS(…))`（版が同じなら同じ内容。`producer.build` は入れない）。
- `artifact_id = "art:" + sha256(JCS({content_id, session_id, observation_id, producer_build, parents}))`。
- `seq`・`produced_at`・`extensions` は id に入れない。`observed_at` も §2.1 の欄の列挙に無いので入れない。
- 配列：`policy_refs`・`rule_refs`・`ordered: false` の役割は集合として整列し重複を禁じる。`ordered: true` は渡した順。役割は名前の UTF-8 バイト順。
- `session_id`（実験）＝`"ses:" + sha256(JCS({experiment_spec_hash, item_id, condition, replicate, rng_seed}))`、`observation_id = "obs:" + sha256(JCS({session_id, ordinal}))`。

## 5 の 0. 構文解析の段（Integration Gate の最初）

数のトークンは整数（`-?(0|[1-9][0-9]*)`）だけ。`1.0`・`1e0`・`NaN`・`Infinity` は拒否。同じオブジェクトの重複キーは、
Unicode のエスケープを戻した後で比べて拒否（正規化はしない）。UTF-8 でないバイト列、孤立したサロゲートも拒否。
この検査を通ったものだけをスキーマと JCS に渡す。スキーマは構造、構文解析と Gate は数の表し方の検査。

## 7. 数の表し方（決定：刻みの整数）

封筒の中は整数だけ。欄ごとにスキーマで量子化を宣言（刻みは 2 の冪 `2^exponent`）。`q = round_ties_to_even(value × 2^(−exponent))`。
`×2^(−exponent)` は `math.ldexp`（誤差なし）。丸めは言語の標準に任せず ties-to-even に固定。
**Python は組み込みの `round()`**（浮動小数に対して ties-to-even。設計書 §7 の「`math` の `round` ではなく `numpy.rint`」は誤り。ここでは `round()` を使い、NumPy を要しない）。Rust は `f64::round_ties_even`。
範囲は ±(2^53−1)（Blob の int64 は別）。NaN・無限大・範囲外は量子化の前に拒否（推測で丸めない）。
大きな配列は封筒の外の Blob（整数の Blob が標準。浮動小数の Blob は理由つきの例外）。

## 8. 意味の不変条件（JSON Schema の外）

| # | 不変条件 |
|---|---|
| S1 | 軌跡の点の `token_index` は狭義に増える |
| S2 | 計測の `calibration_ref` の `space_id` は、計測した軌跡の `space_id` と同じ |
| S3 | 1 本の軌跡の計測に 4 値の判定を付けない（判定は 2 本の比較だけ） |
| S4 | MSR・MM・照合器・CLE の成果物は kind＝interpretation だけ。Selection は HANKO だけ |
| S5 | `parents` は、その成果物より前の `seq` のものだけ（nvs-runtime の受け取りの順序。観測の時刻とは別） |
| S6 | 照合器の U は、後の成果物で消えない |
| S7 | `uncertainty` は `method` の違うものどうしで比べない・合算しない |
| S8 | `observation_id` は三つの場合のどれか（根の観測は nvs-runtime の採番／派生は親から受け継ぐ／観測をまたぐなら null）。入力の参照は `artifact_id` だけ |
| S9 | Governance の `stop`・`hold` の後の再開には、HANKO の Selection が要る |
| S10 | CLE の結果の親は、入力の役割の表とちょうど一致する |
| S11 | 想起の結果は、保存した封筒とバイト単位で同じ。想起は新しい経験を作らない |
| S12 | 想起の結果を親に持つ成果物には、その想起の出来事も親にある |
| S13 | `single`：calibration の `space_id` ＝計測の `space_id`。`pair`：加えて calibration の `between_alignment` ＝比較の `alignment.mode` |
| S14 | 同じビルドで同じ実験を流し直すと、`content_id` と `artifact_id` が一致する |
| S15a | 同じビルドで同じ入力なら、量子化した整数がすべて一致し `content_id` も一致する |
| S15b | 同じ版の別のビルドでは、各欄の整数の差が `tolerance_quanta` 以下（浮動小数の Blob は宣言した比較の規則） |
| S16 | `content_id`・`artifact_id` に入る配列が §2.1 の規則どおり。payload のスキーマのすべての配列に `x-sensos-ordered` がある |
| S17 | `alignment.mode`／`between_alignment` が `x-common_prefix` なら、封筒の `extensions.x-meaning-space-runtime-alignment` に `{reason, approved_by}` |
| S18 | 比較（pair）：左右の `space_id`・`model_build_id`・`dimension` が同じ。`equal_only` なら `length` が同じで `points_used` がそれと等しい |
| S19 | calibration：下限 ≤ 上限、`floor[0] < floor[1]`、`null_set` の id の集合＝封筒の役割 `null_set` の id の集合、件数＝`sample_config.trajectories` |
| S20 | 計測の payload の `calibration` ＝封筒の `calibration_ref`、かつ役割 `calibration` の親でもある |
| S21 | calibration の `values.codebook_ref` ＝封筒の役割 `codebook` の親（無ければ両方無い） |
| S22 | 想起の出来事を親に持つ成果物は、その保存（`seq`）より後に受け取られる |
| S23 | `thresholds.source.X` が `calibration` なら、`thresholds.X` は `calibration_ref` が指す calibration の `values.X` と同じ整数 |
| S24 | 整数の Blob だけ：sha256 は正規のバイト列（int64、リトルエンディアン、C の順、ヘッダなし）で計算。ファイルの長さ＝要素数×8 |
| S25 | 浮動小数の Blob だけ：封筒の `extensions.x-<部品名>-float-blob` に理由。長さ＝要素数×要素のバイト数。S15b は宣言した `comparison` |

この版の参照実装（`tools/contracts/check.py`）が検査するのは、IC-00 だけで確かめられる S4・S5・S8・S16 と、スキーマ・id の計算し直し・親の既知。
S1〜S3・S6・S7・S9〜S15・S17〜S25 は payload や他部品が要るので、この版では未実装（各部品の試験で）。

## 9. 契約の試験（3 段）

1. スキーマの検査（スキーマ自体の妥当性、lock の sha256 の一致）。2. 意味の不変条件の試験（S1〜S25）。3. 部品をまたぐ往復の試験。
見本の成果物（正しい例と拒否されるべき例）は契約の版に属し、契約を変えたら見本も変える。

## 設計書が定めていない点を、この実装で決めたところ（設計書の更新で確定させる）

- `content_id` の入力のキー名：`producer` は `{name, version}`、`calibration_content_id`（null あり）、`parent_contents`。
- `policy_refs` の整列は `(name, sha256)`（設計書 §2.1 は `(name, version, sha256)` と書くが `policy_refs` に `version` は無い）。整列は欄ごとの UTF-8 バイト列の辞書順。
- S4 の `producer.name`：`nvs-kernel`（Edge）・`nvs-runtime`・`hekb-vnext`・`hext`・`meaning-mapper`・`meaning-space-runtime`・`categorical-lift-engine`・`sensos-ux`、接頭辞 `adapter:`・`capability:`。
- `session_id`・`observation_id` の形式は `^ses:[0-9a-f]{64}$`・`^obs:[0-9a-f]{64}$`。実運用の `session_id` は 256 ビットの乱数。`ordinal` は 0 から。
- `observed_at` は HEXT v2（`hext-2.schema.json`、`v2-draft`）の `time.observed_at` と同じ形（null か `pointInTime`）。
- `parents[].artifact_ids` の `x-sensos-ordered` は静的に `true`（順序の意味は兄弟の `ordered` で決まる。`false` のときの整列は S16 の検査）。
- `uncertainty` の `value`・`scale` の型（量子の個数と `{base: 2, exponent}`）。
