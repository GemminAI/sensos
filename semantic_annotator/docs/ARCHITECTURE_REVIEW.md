# Architecture Review: semantic-annotator as the SensOS Observation Layer

本ドキュメントは、SensOS vNext における Observation-Centered Intelligence (OCI) /
Observation-First Architecture の文脈で、`semantic-annotator` を
**Observation Layer** として完成させる前段の設計レビューである。実装は含まない。

```
Reality → Observation Source → Observation → semantic-annotator
  → Annotated Observation → Semantic Projection (EXP-5100)
  → Knowledge Category (EXP-7100) → Reference Universe Compiler (EXP-7500)
```

`semantic-annotator` の責務は「Observation を標準化し Annotation を付与すること」
のみであり、知識生成・推論・Projection・Reference Universe 構築は行わない。

---

## 1. 現状の構成

```
src/semantic_annotator/
  models.py      Observation / Annotation / AnnotatedObservation (frozen dataclass)
  annotator.py   Annotator Protocol + PassthroughAnnotator / KeywordAnnotator
  pipeline.py    run_pipeline(): Iterable[Observation] -> Iterator[AnnotatedObservation]
  cli.py         NDJSON stdin/stdout アダプタ、argparse
  __main__.py    `python -m semantic_annotator`
tests/           models / annotator / pipeline / cli をそれぞれミラーしたユニットテスト
docs/ARCHITECTURE.md   既存の設計ドキュメント（本レビューの前提）
Dockerfile       multi-stage, non-root user, uv ベース
.github/workflows/ci.yml   lint (ruff) / typecheck (mypy strict) / test (pytest) / docker build
pyproject.toml   ランタイム依存ゼロ、mypy strict、ruff、pytest-cov
```

**モジュール依存方向**: `cli` → `pipeline` → `annotator` → `models` の一方向。
`models` と `annotator` はCLIやI/O形式を一切知らない。循環依存なし。

**Observationモデル**: `id`, `source`, `timestamp`, `payload: dict[str, Any]`。
frozen + slots の dataclass で不変。

**AnnotatedObservationモデル**: 元の `observation` を保持したまま
`annotations: tuple[Annotation, ...]`, `annotated_at`, `annotator_version` を付加。
`Annotation` は `label`, `confidence`(0〜1を`__post_init__`で検証), 任意の `taxonomy` 参照。

**Annotator Protocol**: `annotate(observation: Observation) -> AnnotatedObservation` の
1メソッドのみの `runtime_checkable Protocol`。同期・単発呼び出しのみを想定。

**Pipeline**: `Iterable[Observation]` を受け取り、`Annotator` を1件ずつ適用して
`Iterator[AnnotatedObservation]` を遅延生成するだけ。バッチ化・並列化・エラー処理なし。

**CLI**: NDJSON を1行ずつ `Observation` にパースし、`run_pipeline` を通して結果を
NDJSON で書き出す薄いアダプタ。`main()` は `PassthroughAnnotator` をハードコードしており、
アノテーター選択はコード変更でしか行えない。

**Docker**: multi-stage build、依存とソースのレイヤー分離、非rootユーザーで実行。
妥当な最小構成。

**テスト**: 4ファイルすべてが対応するモジュールと1対1。confidence境界値、
キーワードマッチ／非マッチ、パイプラインの順序保証、CLIの空行スキップなど
基本的な正常系・境界値は押さえている。異常系（不正な入力、Annotatorが例外を送出する場合）
のテストは無い。

**CI**: lint / mypy strict / pytest / docker build の4ジョブが独立して走る。
カバレッジは計測しているが閾値によるゲートはない。

---

## 2. 良い点

- **一方向依存と関心の分離が徹底されている。** `models` は純粋なデータ型、
  `annotator` は戦略、`pipeline` はオーケストレーションのみ、`cli` は入出力アダプタ。
  ドメインロジックがI/Oやトランスポートの詳細から完全に独立している。
- **`Annotator` が Protocol で定義されている。** 具象実装への依存が構造的に
  排除されており、将来 embedding/LLMベースの Annotator を追加しても
  `pipeline`・`cli` は無変更で済む。既存の `docs/ARCHITECTURE.md` にも
  この意図が明記されている。
- **ランタイム依存ゼロ。** アノテーション戦略を後から選ぶための余地が
  意図的に残されている。
- **不変データモデル。** `frozen=True, slots=True` により、Observation が
  パイプラインを通過する間に書き換えられる余地がない。Observation-First
  Architecture が要求する「Observationは事実として不変である」という
  前提と自然に合致している。
- **ストリーミング設計。** ジェネレータベースのため無限ストリームに対応でき、
  将来のスケール要求（センサーからの継続的な入力）と整合する。
- **CI/Docker/pre-commitが最初から揃っている。** スキャフォールドの段階で
  品質ゲートが機能する状態になっている。

---

## 3. OCIとの整合性

- **責務境界は正しく守られている。** 現状のコードは「意味の解釈（ラベル付与）」
  はするが、それ以上の知識化・推論・Projectionには一切踏み込んでいない。
  `KeywordAnnotator` も単純な文字列マッチであり、推論とは呼べない。
  `docs/ARCHITECTURE.md` の "Out of scope" 節が Projection/Knowledge/Reference
  Universe を明示的に除外しており、設計思想の理解が既に反映されている。
- **ただし「Observation Layer」としての境界の反対側（Reality → Observation Source →
  Observation）に対する責務がまだ薄い。** 現状は「正しい形のJSONが来る」ことを
  前提にしており、Observation Source側の多様性（センサー種別、欠損フィールド、
  不正なpayload、順序保証のないイベント到着）を吸収する層が存在しない。
  OCIにおいて semantic-annotator が Observation Layer である以上、
  「標準化」は annotation付与だけでなく、**多様な Observation Source から来る
  生データを単一の Observation 契約に正規化する** ことも含意するはずである。
  現状の `_parse_observations` はこの正規化をほぼ素通しで行っており（欠損キーは
  `KeyError` で即座に落ちる）、Observation Source の多様性を吸収する責務が
  実質的に果たされていない。
- **`AnnotatedObservation` → `Semantic Projection (EXP-5100)` への出力契約が
  暗黙的。** 現在の出力は「このプロセスの標準出力に流れるNDJSON」でしかなく、
  Semantic Projection 側が何をどう受け取るかという契約（スキーマバージョン、
  配信保証、順序保証、冪等性）が明文化されていない。Observation Layer が
  「後続コンポーネントの責務を侵さない」ことと、「後続コンポーネントが
  安心して依存できる安定した出力契約を提供する」ことは別の要求であり、
  後者がまだ弱い。
- **Annotator が推論をしていないことの保証が構造的でない。** Protocolは
  `annotate()` の型シグネチャしか強制しておらず、将来誰かが「LLMで意味を
  解釈してKnowledge Categoryまで割り当てる」Annotatorを書いても、型システムは
  それを止めない。責務逸脱を防ぐ設計上のガードレール（例: Annotationの形状に
  制約を課す、taxonomy参照は既存カテゴリのIDのみを許可し自由記述のKnowledge
  生成を許さない、など）が今のところコメントとドキュメントのみに依存している。

---

## 4. Observation Layerとして不足している点

1. **入力側の正規化・検証層がない。**
   `cli._parse_observations` は生JSONの必須キー欠如やタイムスタンプ不正で
   即座に例外を送出し、ストリーム全体を止める。Observation Source の
   多様性（欠損、型不一致、未来/過去日時、重複ID）を吸収する専用の
   検証・正規化ステップが存在しない。

2. **エラーハンドリング方針が未定義。**
   `Annotator.annotate()` が例外を送出した場合、`pipeline`はそれを
   そのまま伝播させ、ストリーム全体が停止する。1件のObservationの
   異常が全体を落とすのは、継続的なReality入力を扱う層としては脆弱。
   「スキップして継続」「デッドレターに退避」「フェイルファスト」の
   いずれを既定にするかの方針とその実装インターフェースがない。

3. **Annotator選択がハードコードされている。**
   `cli.main()` は `PassthroughAnnotator()` を直書きしており、
   `KeywordAnnotator` すら設定なしに選べない。「Annotation戦略は
   エッジで選択可能」という設計目標（ARCHITECTURE.md）に対し、
   現状のCLIはこれを体現していない。

4. **複数Annotatorの合成（Composite）がない。**
   実運用では複数の戦略（keyword + embedding + ルールベース等）を
   同時に走らせ、結果をマージ／重複排除／優先順位付けする必要が
   出てくるが、その合成点となるインターフェースがない。

5. **非同期・I/Oバウンドな Annotator を想定していない。**
   `Annotator.annotate()` は完全同期。embeddingモデルやLLM呼び出しなど、
   ネットワークI/Oを伴う将来のAnnotatorを想定すると、同期Protocolのままでは
   パイプライン全体がブロッキングになる。`AsyncAnnotator`相当の型も、
   `pipeline`側の非同期実行経路も現状存在しない。

6. **観測可能性（Observability）がない。**
   Observation Layerは継続稼働するインフラコンポーネントであるにも関わらず、
   構造化ログ、メトリクス（処理件数、Annotator別のレイテンシ・成功率）、
   トレーシングの差し込み点が一切ない。

7. **出力契約のバージョニングが不十分。**
   `AnnotatedObservation` には `annotator_version` はあるが、
   Observation/AnnotatedObservationという**契約そのもの**のスキーマバージョンが
   存在しない。Semantic Projection (EXP-5100) 側がこの契約に依存する以上、
   将来のフィールド追加・変更を非破壊的に行うための版管理が必要。

8. **冪等性・重複排除の概念がない。**
   同一Observationが再送された場合の扱い（冪等に同じ結果を返す、
   重複としてスキップする等）が未定義。`annotated_at`が
   `datetime.now(UTC)`である以上、同じ入力に対して出力が毎回変わり、
   厳密な意味で冪等ではない。

9. **Observationの出所・信頼度（provenance/trust）を扱う場所がない。**
   `source: str` はあるが、それが登録済みの既知ソースかどうかの検証、
   ソースごとの信頼度・優先度をAnnotationの確信度計算に反映する仕組みがない。

10. **バックプレッシャー・バッチ処理がない。**
    ストリーミング前提だが、Annotatorがボトルネックになった場合の
    バックプレッシャー機構や、スループットのためのバッチ化経路がない。

---

## 5. 今後追加すべきインターフェース

Observation Layerとしての責務（標準化 + Annotation付与）の枠内で、
以下のインターフェースの追加を推奨する。いずれも「意味の理解・推論・
Projection」には踏み込まない。

- **`ObservationSource` 正規化インターフェース**
  生入力（センサー固有フォーマット、部分的フィールド欠損など）を
  `Observation` へ正規化する層。`raw -> Observation | ObservationValidationError`
  の形の変換契約とし、`cli`の`_parse_observations`をこの上に再構築する。

- **`AnnotationError` / エラーハンドリングポリシー**
  Annotatorが失敗した際の型（`AnnotationError`）と、`pipeline`側で
  「スキップ+ログ」「デッドレター出力」「フェイルファスト」を選べる
  ポリシー引数（例: `on_error: ErrorPolicy`）。

- **`AnnotatorRegistry` / ファクトリ**
  名前→Annotatorのマッピングを保持し、CLIや将来の設定ファイルから
  文字列キー（例: `"keyword"`, `"passthrough"`）でAnnotatorを選択できる
  ようにする。`cli.main()`のハードコードを解消する。

- **`CompositeAnnotator`**
  複数の`Annotator`を実行し、`AnnotatedObservation.annotations`を
  マージ・重複排除するための合成実装。既存の`Annotator` Protocolを
  そのまま満たすため、`pipeline`側の変更は不要。

- **`AsyncAnnotator` Protocol と非同期パイプライン経路**
  `async def annotate(...) -> AnnotatedObservation` を持つ非同期版Protocol
  と、それを駆動する`run_pipeline_async`。I/Oバウンドな将来のAnnotator
  （embedding/LLM呼び出し等）を、既存の同期経路を壊さずに追加できるようにする。

- **契約バージョンフィールド**
  `Observation`/`AnnotatedObservation`に`schema_version`相当のフィールドを
  持たせ、Semantic Projection側との後方互換な進化を可能にする。

- **観測可能性フック**
  `pipeline.run_pipeline`にオプショナルな`on_annotated` / `on_error`
  コールバック、またはメトリクス用の軽量なイベントインターフェースを追加。
  実装（Prometheus等）は導入せず、フックの形だけ用意する。

- **冪等性・重複排除のための`ObservationKey`**
  `Observation.id` + `source`から一意キーを導出し、`pipeline`または
  その手前で重複を検出できるインターフェース（実装はin-memoryのみで可、
  永続ストアはSensOS側の責務）。

---

## 6. 推奨ロードマップ

**フェーズ0（現状）**: 単一Annotator・同期・エラー未処理のスキャフォールド。
契約は概ね固まっているが、実運用の入力の乱雑さ・障害・複数戦略の合成に耐えない。

**フェーズ1 — 入力の頑健化**
入力正規化層（`ObservationSource`検証）とエラーハンドリングポリシー
（`AnnotationError` + `on_error`）を追加。異常系のテストを追加。
CLIレベルでAnnotator選択を設定可能にする（`AnnotatorRegistry`）。
→ Reality層からの多様な入力に対して落ちない状態にする。

**フェーズ2 — 戦略の合成と拡張**
`CompositeAnnotator`を追加し、`KeywordAnnotator`以外の戦略
（ルールベース、外部APIベース等）を組み合わせられるようにする。
契約バージョンフィールドを`Observation`/`AnnotatedObservation`に追加。

**フェーズ3 — 非同期・スケール対応**
`AsyncAnnotator` Protocolと非同期パイプライン経路を追加。
観測可能性フック（ログ/メトリクス）を導入し、Docker/CIにパフォーマンス
回帰の検知（簡易ベンチマーク）を組み込む。

**フェーズ4 — サービス化の準備**
冪等性・重複排除のインターフェースを整備。ネットワーク越しのトランスポート
（HTTP/queue consumer）を、既存の`pipeline`/`annotator`を変更せずに
追加できることを実証する（ARCHITECTURE.mdの拡張ポイントの検証）。
この段階で初めて、Semantic Projection (EXP-5100) が依存できる安定した
配信契約（順序保証・at-least-once/at-most-onceの明記等）を確定する。

各フェーズとも、Knowledge生成・推論・Projection・Reference Universe構築には
一切踏み込まない。それらは一貫して後続コンポーネントの責務として明確に
線引きし続けることを、ロードマップ全体の前提とする。
