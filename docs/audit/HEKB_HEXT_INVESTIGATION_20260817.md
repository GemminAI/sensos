# HEKB / HEXT 現状機能・責務・接続可能性 調査報告

**調査日:** 2026-08-17
**調査範囲:** `/Users/tomonam3/GemminAI/hekb` (git HEAD `d960673`), `/Users/tomonam3/GemminAI/hext` (git HEAD `94c728a`)
**方針:** README のみで判断せず、実コード・テスト・設定・API定義を実際に読んで確認。ドキュメント上の主張と実装の区別を明示。存在しない接続・機能は「存在しない」と明記し、推測で補完しない。
**制約:** 今回はコードを変更していない。使用したツールは `Read`・`grep`・`git status`/`git log`・既存テストの実行（`pytest`、およびビルド済み C++ テストバイナリの実行）のみ。新規ビルド・新規サービス起動は行っていない。

**証跡の階層:** SPEC(仕様文書) < CODE(実コード) < CONFIG < LIVE ENDPOINT < WIRE-LEVEL TRACE。本調査で到達できたのは CODE と、既存テスト実行による「テスト結果」のみ。稼働中の `hekbd`/`hekb-api` に対する LIVE ENDPOINT / WIRE-LEVEL の検証は、「新規に外部サービスを起動しない」という今回の制約により意図的に NOT_EVALUABLE。

---

## 1. 調査方針（実施内容の要約）

- 両リポジトリの `git log` / `git status` / ディレクトリ構造を確認。
- HEKB: `python/hekb/` 配下の全実装モジュール（`model.py`, `codec.py`, `store.py`, `client.py`, `api.py`, `api_storage.py`, `query.py`, `mcp.py`, `cli.py`, `compiler.py`, `conformance.py`）を全文読了。C++ 側は `cpp/server/http_api.hpp` とルート定義（`http_api.cpp` の grep）を確認。
- HEXT: 実行可能コードの有無を明示的に検索（`.py/.js/.ts/.go/.rs/.cpp/.java` を再帰検索、ヒット0件）。`SPECIFICATION.md`、`schemas/hext-core.xsd`、`docs/json/mapping.md`、`docs/canonicalization.md`、`docs/object-graph.md`、`docs/query-model.md` を全文読了。
- 既存テストを実行（新規ビルドなし、既存の pytest 環境・既存のビルド済み C++ バイナリのみ使用）。
- 両リポジトリ相互のドキュメント/コード内で、互いへの直接参照があるかを `grep` で確認。

---

## 2. HEKB 調査

### A. 基本情報

| 項目 | 内容 | 根拠 |
|---|---|---|
| リポジトリの目的 | 「知識オペレーティング基盤」("A knowledge operating substrate")。事実(fact)をコンテンツアドレス方式で保存し、関連付け、検索する | [README.md:7-11](/Users/tomonam3/GemminAI/hekb/README.md) |
| パッケージ構成 | 二重実装: C++ デーモン `hekbd`(`cpp/`) + Python パッケージ `hekb`(`python/hekb/`) | ディレクトリ構造(本ターンで確認) |
| 言語 | C++（コアデーモン、`cpp/server`, `cpp/src`）+ Python 3.12（リファレンス実装・API・CLI・MCP、`python/hekb/`） | `python/pyproject.toml:47` (`target-version = "py312"`) |
| エントリポイント | `hekbd`（C++バイナリ）／`hekb-mcp`／`hekb-api`（Python コンソールスクリプト）／`hekb`（CLI） | `python/pyproject.toml:36-37` (`hekb-mcp = "hekb.mcp:main"`, `hekb-api = "hekb.api:main"`) |
| 起動方法 | `./build/hekbd`（ストア）→ `hekb-mcp`（stdio MCPサーバ、`HEKB_URL` 経由でストアに接続） | [docs/MCP.md:20-28](/Users/tomonam3/GemminAI/hekb/docs/MCP.md) |
| 分類 | ライブラリ + CLI + HTTP API(二種類) + MCP サーバ、の複合体 | 上記各エントリポイントの実在確認 |
| 現在バージョン | `1.0.0`（実装バージョン。スキーマ識別子 `hext.object/1`/`hext.morphism/1` は別管理） | [python/pyproject.toml:7](/Users/tomonam3/GemminAI/hekb/python/pyproject.toml), [python/hekb/__init__.py:47](/Users/tomonam3/GemminAI/hekb/python/hekb/__init__.py), [CHANGELOG.md:9-13](/Users/tomonam3/GemminAI/hekb/CHANGELOG.md) |
| git HEAD | `d960673724184b9d9941e8989b168d778cf8cf9e`（2026-07-25、"Rewrite README for a three-minute first visit"） | `git log -1` |

### B. 実際の主要機能（コードから特定）

| 機能 | 実装箇所 | 備考 |
|---|---|---|
| オブジェクト保存 | `KnowledgeStore.put()` — [python/hekb/store.py:48-56](/Users/tomonam3/GemminAI/hekb/python/hekb/store.py) | インメモリのみ。永続化は別レイヤ |
| 永続化（SQLite） | `SqliteObjectStore.save()/load_all()` — [python/hekb/api_storage.py:41-51](/Users/tomonam3/GemminAI/hekb/python/hekb/api_storage.py) | `hekb-api`(Python) 専用の単一テーブルインデックス |
| 永続化（C++ コア） | `hekb::storage::FileStore`（`cpp/src/storage/`） | 存在確認は `test_file_store` バイナリの実行(10件PASS、§F参照)による。ソース内容そのものは未読 |
| バリデーション | `validate_object()`/`validate_morphism()` — [python/hekb/model.py:101-146](/Users/tomonam3/GemminAI/hekb/python/hekb/model.py) | |
| コンテンツアドレス／ハッシュ | `compute_object_id()`/`compute_morphism_id()`（BLAKE2b-256） — [python/hekb/codec.py:128-135](/Users/tomonam3/GemminAI/hekb/python/hekb/codec.py) | |
| 正準化(canonicalization) | `canonical_bytes()`/`morphism_canonical_bytes()` — [python/hekb/codec.py:91-125](/Users/tomonam3/GemminAI/hekb/python/hekb/codec.py) | 独自の最小JSON風文字列形式 |
| 封印(identity確定) | `seal()` — [python/hekb/codec.py:138-151](/Users/tomonam3/GemminAI/hekb/python/hekb/codec.py) | 封印されていないオブジェクトは保存不可 |
| クエリ: 最近傍 | `nearest()` — [python/hekb/query.py:69-91](/Users/tomonam3/GemminAI/hekb/python/hekb/query.py) | cosine / euclidean |
| クエリ: 近傍展開 | `neighbours()` — [python/hekb/query.py:94-126](/Users/tomonam3/GemminAI/hekb/python/hekb/query.py) | BFS |
| クエリ: 最短路 | `geodesic()` — [python/hekb/query.py:129-179](/Users/tomonam3/GemminAI/hekb/python/hekb/query.py) | Dijkstra、重みは非負 |
| 関連付け（グラフエッジ） | `KnowledgeStore.relate()` — [python/hekb/store.py:58-77](/Users/tomonam3/GemminAI/hekb/python/hekb/store.py) | 参照整合性チェックあり |
| 削除（カスケード） | `KnowledgeStore.erase()` — [python/hekb/store.py:79-95](/Users/tomonam3/GemminAI/hekb/python/hekb/store.py) | |
| JSONL相互運用 | `export_jsonl()`/`import_jsonl()` — [python/hekb/store.py:132-165](/Users/tomonam3/GemminAI/hekb/python/hekb/store.py) | |
| 適合性検証(conformance) | `generate()`/`verify()` — [python/hekb/conformance.py:211-231](/Users/tomonam3/GemminAI/hekb/python/hekb/conformance.py) | Python実装とC++実装のバイト単位一致を保証する仕組み |
| コンパイラ（別名解決） | `compile_source()` — [python/hekb/compiler.py:135-193](/Users/tomonam3/GemminAI/hekb/python/hekb/compiler.py) | ローカル別名でオブジェクト/モーフィズムを記述しコンパイル |

**明示的に「存在しない」と確認した機能:**
- **Evidence の専用保存機構**: 存在しない。`EVIDENCE` は `HextKind` の一値に過ぎず、本文(body)やフォーマット属性を持つ専用フィールドはない。
- **Trajectory（軌跡）保存**: 存在しない。モデル・ストア・API・MCPのいずれにも trajectory という概念自体が見当たらない。
- **Lineage（系譜）の専用フィールド**: 存在しない。`Morphism`（`DERIVES`等）で表現は可能だが、"lineage" という第一級概念・API・フィールドはない。
- **Attestation（外部署名等）**: 存在しない。`is_sealed()`（[codec.py:154-168](/Users/tomonam3/GemminAI/hekb/python/hekb/codec.py)）はコンテンツアドレスの自己整合性チェックのみで、外部署名検証機構はコード上確認できない。
- **Session/cycle の専用フィールド**: 存在しない。`labels`（自由なstring→stringマップ）で表現可能だが、専用スキーマはない。

### C. データモデル（実際に存在するフィールドのみ）

`HextObject`（[python/hekb/model.py:59-72](/Users/tomonam3/GemminAI/hekb/python/hekb/model.py)）:

```
kind: HextKind        # 閉じた列挙: OBSERVATION/STATE/HYPOTHESIS/EVIDENCE/MEMORY/ENTITY/EVENT/DOCUMENT
created_ns: int
vector: list[float]
attributes: dict[str, float]
labels: dict[str, str]
id: str                # 64桁16進 コンテンツアドレス
```

`Morphism`（[model.py:75-87](/Users/tomonam3/GemminAI/hekb/python/hekb/model.py)）:

```
source: str            # コンテンツアドレス
target: str
kind: MorphismKind      # SUCCEEDS/DERIVES/CONTRADICTS/SUPPORTS/NEIGHBOURS
weight: float
id: str
```

**存在しないと確認したフィールド:** `state_hash`、`trajectory`、`evidence`(専用型としては存在せず、`HextKind.EVIDENCE`という値のみ)、`session_id`/`cycle`(専用フィールドとしては存在せず、`labels`で自由に表現可能なだけ)、`lineage`、`provenance`、`ledger`、`seal`、`signature`。これらは後述する外部の HEXT 標準仕様には存在するが、HEKB の `HextObject` には一切存在しない。

### D. API/Interface

**HTTP（C++ `hekbd`、既定ポート8100）** — [cpp/server/http_api.cpp](/Users/tomonam3/GemminAI/hekb/cpp/server/http_api.cpp) のルート登録より:

```
GET    /health
GET    /version
GET    /metrics
PUT    /v1/objects/{64桁16進id}
POST   /v1/objects
GET    /v1/objects/{id}
DELETE /v1/objects/{id}
POST   /v1/morphisms
GET    /v1/morphisms/{id}
DELETE /v1/morphisms/{id}
POST   /v1/query/nearest
GET    /v1/query/neighbours
GET    /v1/query/geodesic
```

**HTTP（Python `hekb-api`、FastAPI、既定ポート8080）** — [python/hekb/api.py:123-192](/Users/tomonam3/GemminAI/hekb/python/hekb/api.py):

```
GET  /health
POST /v1/objects
GET  /v1/objects/{id}
POST /v1/search
POST /v1/closure   # 明示的に stub。closure生成は未実装（api.py:182-191、"status": "stub"）
```

**重要な非対称性:** Python版 API は C++版よりも小さいサーフェス（PUT-by-id なし、morphisms エンドポイントなし、`nearest`/`neighbours`/`geodesic` クエリエンドポイントなし）。docstring（[api.py:10-13](/Users/tomonam3/GemminAI/hekb/python/hekb/api.py)）は「両方のスタックが存在してよい理由は `GemminAI/sensos` の ADR-0003 を参照」としており、C++トールチェーンが使えない環境向けの限定的な代替と位置づけられている。

**MCP（`hekb-mcp`、stdio）** — [python/hekb/mcp.py:30-38, 41-143, 146-198](/Users/tomonam3/GemminAI/hekb/python/hekb/mcp.py):

7ツール、すべて実装済み（プレースホルダーなし、テストで保証）:
`hekb_put_object`, `hekb_get_object`, `hekb_relate`, `hekb_nearest`, `hekb_neighbours`, `hekb_geodesic`, `hekb_stats`

**CLI（`hekb`）** — [python/hekb/cli.py:188-265](/Users/tomonam3/GemminAI/hekb/python/hekb/cli.py):
`address`(オフライン), `compile`, `conformance`, `version`, `stats`, `put`, `get`, `delete`, `relate`, `nearest`, `neighbours`, `path`

**Pythonライブラリ直接利用:** `from hekb import HextObject, HextKind, KnowledgeStore` でインプロセス利用可能（README.md クイック例で確認）。

### E. Runtime からの利用可能性

| 項目 | 状態 | 根拠 |
|---|---|---|
| HEKBへの保存 | **今すぐ呼び出し可能**（ライブラリとして）。`pip install hekb` → `KnowledgeStore().put(obj)` は外部依存なしのインプロセス処理 | store.py |
| HEKBへの保存（永続・ネットワーク経由） | **BLOCKED（今回未検証）**。`hekbd`/`hekb-api` の起動が必要。今回は「新規に外部サービスを起動しない」という制約により意図的に未実施 | 制約による NOT_EVALUABLE |
| HEKBへの照会 | インプロセス関数としては**今すぐ呼び出し可能**（query.py）。ネットワーク経由は保存と同様BLOCKED | 同上 |
| Evidence永続化 | `kind=EVIDENCE` の `HextObject` として保存可能だが、専用のbody/formatフィールドは**存在しない**（§C参照） | model.py |
| Observation永続化 | `kind=OBSERVATION` の `HextObject` として保存可能。vector/attributes/labelsのみ、自由テキスト本文フィールドは**存在しない** | model.py |
| Trajectory永続化 | **存在しない**（§B参照）。表現する手段自体がコード上にない | 網羅的読了による確認 |
| Lineage永続化 | 第一級機能としては**存在しない**。`Morphism(kind=DERIVES)` 等でグラフとして表現することは可能 | store.py |

### F. 現在の実測状態

**Python テストスイート**（`python3 -m pytest -q`、本ターンで実行）:
```
169 passed, 1 warning (StarletteDeprecationWarning) in 0.34s
```

**C++ ビルド済みテストバイナリ**（`hekb/build/` に既存、新規ビルドは行っていない）:

| バイナリ | 結果 |
|---|---|
| test_blake2b | 6 PASS |
| test_file_store | 10 PASS |
| test_knowledge_store | 13 PASS |
| test_graph_index | 9 PASS |
| test_validate | 12 PASS |
| test_identity | 11 PASS |
| test_canonical | 11 PASS |
| test_memory_store | 12 PASS |
| test_projection | 10 PASS |
| test_query | 17 PASS |
| **test_conformance** | **3 FAILED** |

**test_conformance 失敗の根本原因（特定済み）:** 例外メッセージに `/Users/tomonam3/nvs-platform-runtime/hekb-core/build/...` というパスがハードコードされている（本バイナリがビルドされた時点でのリポジトリの旧配置パス）。現在の配置は `/Users/tomonam3/GemminAI/hekb` であり、`conformance/vectors/*.txt` はコンパイル時に埋め込まれた旧パス基準の相対参照で解決されているため、現在のファイルシステム上のファイルは実在するにもかかわらず「見つからない」という失敗になっている。**これはPython実装とC++実装の適合性の実際の乖離ではなく、リポジトリ移設後の古いビルド成果物の問題**。再ビルドすれば解消する可能性が高いが、今回は「新規ビルドを行わない」という制約のため再検証していない。→ **NOT_EVALUABLE（再ビルドが必要、今回スコープ外）**。

**Live endpoint 検証:** 実施せず。ユーザー指示「新規に外部サービスを起動しない」に従い、`hekbd`/`hekb-api` の起動・接続確認は行っていない。→ **意図的 NOT_EVALUABLE**。

**git status（変更なし、確認のみ）:**
```
 M .dockerignore
 M .gitignore
 M docker/docker-compose.yml
 M python/pyproject.toml
?? docker/Dockerfile.api
?? docs/hekb-api.md
?? python/hekb/api.py
?? python/hekb/api_storage.py
?? python/tests/test_api.py
?? python/uv.lock
```
上記はすべて調査開始前からの既存の未コミット差分（今回は `Read`/`grep`/`git`/`pytest`/既存バイナリ実行のみで、`Write`/`Edit` は一切使用していない）。

---

## 3. HEXT 調査

### A. 基本情報

| 項目 | 内容 | 根拠 |
|---|---|---|
| リポジトリの目的 | "The Semantic Object Standard" — 知識を決定論的・検証可能な Semantic Object Graph として表現するための、オープンでプラットフォーム非依存な標準 | [SPECIFICATION.md:1-19](/Users/tomonam3/GemminAI/hext/SPECIFICATION.md) |
| HEXTとは何か | Semantic XML を正準シリアライゼーションとする仕様。README曰く「OpenAPIのJSON/HTTP版のようなもの」 | [README.md:19-23](/Users/tomonam3/GemminAI/hext/README.md) |
| パッケージ構成 | `SPECIFICATION.md`(規範)、`schemas/*.xsd`(規範)、`docs/*`(参考情報)、`examples/*`、`history/*`(非規範アーカイブ)、`registry/README.md` | ディレクトリ構造 |
| 実行可能コード | **ゼロ**。`.py/.js/.ts/.go/.rs/.cpp/.java` を再帰検索した結果、ヒット0件（`.git`除く） | 本ターンで実施した明示的検索 |
| バージョン | `1.0.0`（コア名前空間 `urn:gmm:hext:core:1` は変更なし） | [SPECIFICATION.md:188-196](/Users/tomonam3/GemminAI/hext/SPECIFICATION.md) |
| エントリポイント / 起動方法 | 該当なし（実行可能な成果物が存在しない） | 上記コード検索結果 |
| 分類 | 仕様書リポジトリのみ。ライブラリでも、CLIでも、APIでも、サービスでもない | 上記 |
| git HEAD | `94c728a7fa3072088e27a84513765f10554f072d`（2026-07-26）、`git status` はクリーン | `git log -1`, `git status --short` |

### B. HEXT Object Model（実際の定義、`hext-core.xsd`より）

```
hext:Document (@specVersion required)
  ├─ hext:Object (@id, @type, @lifecycle?, @registryRef?)
  │    └─ hext:Metrics? (@characters?, @lines?, @paragraphs?, @tokensEstimated?)
  ├─ [拡張ポイント: 他名前空間の要素、任意]
  ├─ hext:Provenance (required)
  │    ├─ DerivedFrom? (URI)
  │    ├─ Contributors? ([Contributor(@agent,@role)])
  │    └─ Agency? (@humanTouch 0.0-1.0, @primaryGenerator)
  ├─ hext:Semantic? (optional)
  │    ├─ Instrument? (@type, @version)
  │    ├─ Measurement? (@coordinateSystem, @windowMethod, WindowCalibration?)
  │    └─ ObservationRef? (opaque URI — 「観測システムへの不透明な参照」)
  ├─ [拡張ポイント]
  ├─ hext:Ledger (required) — Entry[] (@t, @type∈{AI,HUMAN,REVIEW,APPROVAL,SYSTEM}, @delta?, @hash)
  ├─ hext:Seal (required) — @sealedAt, @stateHash, Signature?(@algorithm)
  ├─ hext:Evidence (required) — @format + 本文
  └─ [拡張ポイント]
```

`vector`（埋め込みベクトル）、`attributes`（自由なfloatマップ）、`labels`（自由なstringマップ）に相当するフィールドは**コアスキーマのどこにも存在しない**。

### C. HEXT Kind/Type System

| 確認対象 | 結果 |
|---|---|
| `hext:Object/@type` | **自由形式の文字列**（`xs:string`、列挙制約なし）。例: `"document.rfc"`（[mapping.md:39](/Users/tomonam3/GemminAI/hext/docs/json/mapping.md)）。HEKBの閉じた`HextKind` enumとは根本的に異なる型システム |
| `OBSERVATION` | **存在しない**。最も近い概念は `Semantic/ObservationRef` だが、これは「外部観測システムへの不透明なURIプレースホルダ」であり、観測データそのものではない。仕様書本文が明示: 「Observation algorithms, measurement pipelines, or annotator semantics — those belong to external systems」（[SPECIFICATION.md:81](/Users/tomonam3/GemminAI/hext/SPECIFICATION.md)） |
| `EVIDENCE` | **存在するが性質が異なる**。`hext:Evidence`は「kind/typeの値」ではなく、Document直下の必須構造コンテナ（format+本文） |
| `TRAJECTORY` | **存在しない**。スキーマ・仕様書テキストのいずれにも出現しない |
| `STATE` | **存在しない**（kind/type値としては）。最も近い概念は `Seal/@stateHash` だが、これは整合性シールのハッシュフィールドであり、オブジェクト種別ではない |
| 唯一の閉じた列挙 | `Entry/@type` ∈ {AI, HUMAN, REVIEW, APPROVAL, SYSTEM}（誰が/何が台帳エントリを作ったか、であってHEKBの「オブジェクトの種類」とは無関係） |

### D. Serialization/ABI

- **正準形式**: Semantic XML（名前空間 `urn:gmm:hext:core:1`）。「JSON等の他形式はプロジェクションであり、正準XMLを上書きしてはならない（MUST NOT）」（[SPECIFICATION.md:98](/Users/tomonam3/GemminAI/hext/SPECIFICATION.md)）
- **JSON**: 明示的に非正準の「トランスポート・プロジェクション」。snake_caseフィールドマッピング表あり（`spec_version`/`object`/`provenance`/`semantic`/`ledger`/`final_seal`/`evidence`） — [docs/json/mapping.md:20-32](/Users/tomonam3/GemminAI/hext/docs/json/mapping.md)
- **正準化/ハッシュ**: W3C Canonical XML (C14N) → SHA-256 → `state_hash = "sha256:" + 64桁16進`（[docs/canonicalization.md:24-39](/Users/tomonam3/GemminAI/hext/docs/canonicalization.md)）。**HEKBのBLAKE2b-256・独自文字列正準形式とは完全に異なるアルゴリズム・出力形式**（プレフィックスの有無も含めて）
- **スキーマ検証**: XSDベース、「Validator Compliance」プロファイルとして定義（SPECIFICATION.md §6.IV）
- **バージョン互換性**: 仕様自体はSemVer。2.1.0以前にシールされた文書には旧ハッシュ規則を遡及適用しない「grandfather clause」あり。加えて、XMLとは別系統のレガシー `.hxt`（Markdown埋め込みJSON、v0.1.0）形式も存在し、そちらは本文のSHA-256という別規則を持つ（[canonicalization.md:75-97](/Users/tomonam3/GemminAI/hext/docs/canonicalization.md)）

### E. Runtime利用可能性（評価のみ、実装は行っていない）

**評価: SensOS Runtime が HEXT を Observation/Evidence の共通ABIとしてそのまま使うことは、現状のスキーマからは困難であり、アダプタが必要と評価する。** 根拠:

1. HEXTのObjectモデルには `vector`/`attributes`/`labels` に相当するフィールドが一切ない。埋め込みベクトルを扱う用途には構造的に対応していない。
2. HEXT自身が観測アルゴリズム・観測セマンティクスを標準化しないと明言している（`ObservationRef`は不透明URIのみ）。
3. HEXTの正準形式はXMLだが、今回読んだ範囲（HEKB全体）でXMLの生成・パース・C14N正準化・SHA-256シールを行うコードは一切見つからなかった。HEKB側はJSON/独自文字列正準形式・BLAKE2bのみで完結しており、HEXT仕様が要求する正準化手続きを実装していない。

### F. MCPとの関係

- HEXT自身のMCP実装: **存在しない**（実行可能コードがゼロであることは既に確認済み）。
- 仕様書は「MCP Compliance」という**任意の適合プロファイル**を定義しているのみ（[SPECIFICATION.md §6.II](/Users/tomonam3/GemminAI/hext/SPECIFICATION.md)）。これは「MCPを提供する実装が満たすべき要件」であり、HEXT自体がMCPサーバを実装するという意味ではない。
- **MCP=トランスポート、HEXT=意味的オブジェクト契約、という分離は仕様上明確に意図されている**: 「MCP itself is an external protocol; this profile only defines HEXT expectations when MCP is offered」（SPECIFICATION.md:162）。`docs/json/mapping.md:122-125`も「JSON projections are a convenient payload shape for tool responses. Concrete tool names are defined by that implementation」と明記。
- **しかし、実際に確認できた実装（HEKBの`hekb-mcp`）はこのプロファイルを満たしていない**: `hekb-mcp`の7ツールはHEKB独自の`HextObject`形状（kind/vector/attributes/labels）を運んでおり、HEXT標準のJSONプロジェクション形状（object/provenance/semantic/ledger/final_seal/evidence）ではない。ツール説明文に"Store a HEXT object"（[mcp.py:52](/Users/tomonam3/GemminAI/hekb/python/hekb/mcp.py)）とあるが、これは「HEXTという語をHEKB独自の意味で使っている」だけであり、HEXT標準準拠のオブジェクトではない。

---

## 4. HEKB ↔ HEXT 関係（最重要調査）

> **注記:** ユーザー指示のこのセクションは、コードブロック `HEXT / ↓ / ? / HEKB` の直後でメッセージが途切れており、「?」に対する具体的な問い（複数だったと推測される）の詳細は受信できていません。以下は、セクション1〜3で確認した実証的事実のみに基づき、「?」＝両者を繋ぐ実装・変換・マッピングは実際に何が存在するか、という最も自然な読み方で回答したものです。ユーザーの本来の意図と異なる場合はご指摘ください。

### 4.1 コードレベルの接続: 存在しない

`hekb`リポジトリ全体（`*.md`, `*.py`）に対して以下を検索した結果、**ヒットはゼロ件**でした:

```
grep -rn "GemminAI/hext|HEXT Standard|hext-core.xsd|Semantic Object Standard" hekb/
```

HEKBは、外部の `GemminAI/hext` 標準リポジトリのXSDスキーマ・`SPECIFICATION.md`・名前空間URIのいずれに対しても、インポート・パース・検証・参照のいずれも一切行っていません。

### 4.2 両リポジトリは相互に、明示的に「規範的関係はない」と述べている

- **hext側の明言** — `SPECIFICATION.md`は「HEXTが標準化しないもの」の一つとして名指しで除外: 「Knowledge-base product APIs (for example HEKB)」（[SPECIFICATION.md:83](/Users/tomonam3/GemminAI/hext/SPECIFICATION.md)）
- **hext側のREADME** — 「関連プロジェクト」表でHEKBを「HEXTオブジェクトを保存・索引付けするかもしれない任意の(optional)製品層」と位置づけ、その直前に「これらのプロジェクトのいずれも、この標準を理解・実装する義務はない」と明記（[README.md:106-113](/Users/tomonam3/GemminAI/hext/README.md)）
- **hekb側** — `docs/NVS-Kernel.md`はHEKBとNVS-Kernelの境界線を詳細に文書化しているが、外部の`hext`標準リポジトリへの言及は（コード同様）一切ない

### 4.3 「HEXT」という名前は共有されているが、スキーマは別物

HEKBの `python/hekb/model.py:1` のdocstringは「This module... is the HEXT object model — the reference definition」と自称しており、スキーマ識別子も `hext.object/1` / `hext.morphism/1`（model.py:18-19）です。つまり**HEKBは"HEXT"という語を、外部標準とは独立に、自分自身の内部命名として使用しています**。両者を並べると：

| | HEKBの`HextObject`（model.py） | hext標準の`Object`（hext-core.xsd） |
|---|---|---|
| フィールド | kind, created_ns, vector, attributes, labels, id | id, type, lifecycle, registryRef, Metrics |
| 型システム | 閉じた8値enum | 自由形式文字列 |
| 正準形式 | 独自最小JSON風文字列 → BLAKE2b-256 | XML(C14N) → SHA-256、`sha256:`接頭辞付き |
| 必須の兄弟要素 | なし（Object単体で完結） | Provenance/Ledger/Seal/Evidenceが全てDocument直下に必須 |
| ベクトル/埋め込み | あり | なし |
| Evidence | enumの一値に過ぎない | 独立した必須構造コンテナ(format+本文) |

### 4.4 結論

**図の「?」に対する実証的な回答: HEXT標準とHEKB実装を繋ぐ変換・アダプタ・マッピング層は、両リポジトリの現状のコード・ドキュメントのいずれにも実装されていません。** 両者は「意味的知識オブジェクト」という緩い概念的親近性と"HEXT"という名前を共有しているだけの、独立に設計された別個のシステムです。「HEKBはHEXT標準のリファレンス実装である」という理解は、どちらのリポジトリの実コード・テスト・ドキュメントからも裏付けられず、むしろ両リポジトリの記述はその理解を明確に否定しています。

**接続する場合に必要になる作業（評価のみ、今回は実装せず）:**
1. hextの自由形式`type`文字列とHEKBの閉じた`HextKind` enumの相互マッピング（非可逆: hextの例`"document.rfc"`に対応するHEKB値は存在せず、逆にHEKBの`vector`フィールドに対応するhext側の概念は存在しない）
2. HEKBの`HextObject`が持たない、hextが必須とする`Provenance`/`Ledger`/`Seal`/`Evidence`コンテナの生成または欠落処理の決定
3. どちらのハッシュ・正準形式を「アイデンティティの正」とするかの決定（BLAKE2b vs SHA-256、独自文字列 vs XML C14N — 両方で同一のオブジェクトが同一のidを持つことは、現状の仕組みのままでは不可能）

---

## 付録: 本調査で新たに確認したHEKB名称の衝突（sensosリポジトリ内、参考情報）

以下は今回の調査対象（hekb/hext）そのものではなく、`GemminAI/sensos`側のコードを本セッション内で読んだ際に確認した情報です。今回のスコープ外のため精査は行っていませんが、「今後のRuntime/MCP接続設計」に直接関わるため参考として記載します。**この付録のみ、本ターンでの新規読了ではなく、セッション内の別作業で読んだファイル内容に基づきます。**

- `sensos/integrations/hekb-mcp/tools.py` は、`GemminAI/hekb`の`hekb-mcp`（本報告の§2.D）とは**別の実装**です。ツール名（`observe`, `get_object`, `follow_geodesic`, `estimate_curvature`, `resolve_attractor`, `find_pullback`, `get_trust_manifest`）もオブジェクトの型（`object_id`が**整数**、`curvature`/`energy`/`flux_magnitude`/`potential`等のフィールド）も、`GemminAI/hekb`の実際の`HextObject`（`kind`/`vector`/`attributes`/`labels`、コンテンツアドレスは64桁16進文字列）と一致しません。このファイルは「hekb-runtime REST API (EXP-7100)」という、今回調査した`hekbd`/`hekb-api`とは別物と思われるバックエンドを想定しています。**"hekb-mcp"という名前がsensosリポジトリ内に出てきても、それが`GemminAI/hekb`の実装を指すとは限りません。**
