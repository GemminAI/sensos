# SensOS Knowledge Core & Categorical Architecture Specification

**Document ID**: SPEC-SENSOS-KNOWLEDGE-CORE-001

**Status**: Cognitive Architecture Baseline & System Directive Source

**Core Principle**: "HEXT defines, HEKB persists, SensOS observes, NVS-Kernel determines, and LLM renders."

## 1. Executive Summary & Identity

SensOS は、単なる RAG や分散型データベース、LLM アプリケーションのフレームワークではありません。人間の高次な知的活動・思考軌跡を幾何学的かつ熱力学的な物理量として測定し、圏論（Category Theory）的代数構造の上に保持・制御する「認知オペレーティングシステム（Cognitive OS）」です。

自然言語を「不透明な確率的トークン系列」から「検証可能・決定論的な構造状態（Crystallized State）」へと相転移させ、意味の構造崩壊（Premature Semantic Collapse: PSC）を防ぎつつ、自律的な知識の探索と統合を実現します。

## 2. Triad Core Engine (三位一体のコアエンジン)

SensOS は、厳密に分離された 3 つの数学的・物理的エンジンによって構成されます。

```
                    ┌────────────────────────────────────────┐
                    │                 SensOS                 │
                    │         Cognitive Operating System     │
                    └───────────────────┬────────────────────┘
                                        │
         ┌──────────────────────────────┼──────────────────────────────┐
         ▼                              ▼                              ▼
┌─────────────────┐            ┌─────────────────┐            ┌─────────────────┐
│  HEKB (Memory)  │            │ NVS-Kernel (Phys)│            │   CLE (Brain)   │
│ Category Core   │            │ Geodesic Solver │            │ Categorical Lift│
│ 663-Line Algebra│            │ Potential Field │            │ Functor Mapping │
└─────────────────┘            └─────────────────┘            └─────────────────┘
```

1. **HEKB (Heterogeneous Entity Knowledge Base) — 「不変の知識記憶」**:
    
    - **役割**: 圏論的トポロジー構造の永続化ストレージ。
        
    - **数理的基盤**: 有限集合と関数の圏 $\mathbf{Set}$ 上の関手および可換図式。外部ライブラリ依存ゼロの軽量代数コア（663行）。
        
2. **NVS-Kernel (Navigation Vector Space) — 「ナビゲーションの物理法則」**:
    
    - **役割**: 意味多様体上の「重力」と「曲率 $\kappa$」を計算し、思考軌道を誘起・測定する物理エンジン。
        
    - **数理的基盤**: 微分幾何学、測地線（Geodesics）、ポテンシャル場 $V(\mathbf{s})$、熱力学相動態（Semantic Phase Dynamics）。
        
3. **CLE (Categorical Lift Engine) — 「意味の昇華・結晶化コンパイラ」**:
    
    - **役割**: 曖昧な自然言語（Raw Narrative）からホモトピー不変量やカテゴリ構造（5W1H, SOK, 24TAG）を抽出し、高次構造へ固定する関手（Functor）コンパイラ。
        
    - **数理的基盤**: 圏論的対象（Object）と射（Morphism）の構成、ホモトピー同値判定。
        

## 3. Categorical Lift Engine (CLE) & Mathematical Foundations

### 3.1 CLE as a Functorial Compiler (関手コンパイラとしての CLE)

CLE は高次の判断や感想を語る「思考の主体」ではなく、自然言語空間 $\mathcal{L}$ から意味構造空間 $\mathcal{S}$ への構造保存射（Functor）です。

$$\Phi : \mathcal{L} \longrightarrow \mathcal{S}$$

- **対象の射影 (**$L \mapsto S$**)**: Raw Narrative から 5W1H（Who, To Whom, What, When, Where, Why/How）および 24TAG 座標を確定。
    
- **射の保存 (**$f \mapsto \Phi(f)$**)**: 言語表現の変換（翻訳・要約・反実仮想）を、意味空間における可換射（Morphism）として対応付け。
    

### 3.2 Homotopy Invariants & Cross-Domain Connection (ホモトピー不変量と異分野接続)

CLE は、相異なるドメイン（例: 音楽構造、法解釈、歴史的事件、コードのトポロジー）から代数的位相（Betti 数、接続関係）を抽出し、「構造の型（Type）が準同型である」ことを検出して接続します。これにより、表象に惑わされない本質的なセレンディピティ（異分野接続）を誘発します。

## 4. HEKB: Category-Theoretic Algebra & Reality Consensus

### 4.1 Strict Category Axioms in HEKB

HEKB はアドホックなグラフ DB ではなく、以下の圏の公理を絶対的に強制します：

1. **対象 (Objects / Concepts)**: 幾何学的ペイロードを持つ有限要素集合。
    
2. **射 (Morphisms / Relations)**: 対象間の構造決定関数。
    
3. **合成律 (Composition)**: $g \circ f$ の結合法則の保証。
    
4. **恒等射 (Identity)**: 全ての対象 $A$ に対する $\text{id}_A$ の存在。
    

### 4.2 Naturality Square & Homotopy Update Rule (可換性の厳格検証)

HEKB への新たな知識のコミット・更新は、自然性の四角形（Naturality Square）が可換であることを検証した後にのみ許可されます。

$$ \begin{CD} A @>F(f)>> B \ @VV\eta_AV @VV\eta_BV \ G(A) @>G(f)>> G(B) \end{CD} $$

- 可換性の破壊（Inconsistency）が検知された場合、更新は即座に拒絶（Reject）され、記憶の破綻やハルシネーションの混入を防ぎます。
    

### 4.3 Reality Consensus Engine (現実コンセンサス・エンジン)

複数の独立した観測者（人間、異なる AI モデル、文献データ）からの入力に対し、プルバック極限（Pullback Limit）を計算することで、特定モデルのバイアスに依存しない「客観的な現実の共通部分」を数学的に証明・抽出します。

$$\mathcal{R}_{\text{consensus}} = \varprojlim (O_1 \leftarrow X \rightarrow O_2)$$

## 5. SMMP & 38-Port Observation Matrix

### 5.1 Semantic Measurement Platform (SMMP)

SMMP は、モデル内部の思考状態を非破壊的に測定する「オシロスコープ」です。測定前にゼロ歪みリファレンスによるキャリブレーション（Calibration）を必須とします。

### 5.2 38-Port Observation & Intervention Matrix

38 Ports は、単なる静的機能一覧ではなく、以下の 4 段階の Capability Hierarchy に従って駆動・実測されます。

```
 [ 38-Port Capability Hierarchy ]

  Level 4: Control Utility (制御効用)    ──► 軌道転移を所望の幾何空間へ収束・誘導できるか？
  Level 3: Intervention (介入機能)      ──► LLM 推論状態へ非破壊介入（Re-Melting等）できるか？
  Level 2: Attribution (帰属機能)       ──► 観測変化を特定因果（5W1H要素等）へ紐付けられるか？
  Level 1: Observation (観測機能)       ──► 意味空間上の曲率 κ やテンソル変化を測定できるか？
```

- **11 Stateless Ports**: システムノイズ床および環境基準線を提供する静的観測エンドポイント。
    
- **27 Session-Scoped Ports**: セッション状態に依存し、`observe` 軌跡に対する高精度な観測および DAK（Dynamic Adaptive Knowledge）経由の介入ベクトルの適用箇所。
    

## 6. System Directives for LLM Context & Reasoning Rules

LLM が本プロトコル上で推論を行う際の**不可逆行動指針（System Directives）**：

1. **Observation Before Interpretation (解釈の前に観測せよ)**:
    
    - 感情、面白さ、評価などの抽象的解釈を決定する前に、必ず対象の 5W1H 構造、意味空間における位置移動、曲率変化（$\Delta\kappa$）の物理量を記述・認識せよ。
        
2. **Respect the Deterministic Envelope (JCS / SHA-256 契約の尊重)**:
    
    - 通信・出力境界においては暗黙の変数を排除し、JCS (RFC 8785) に準拠した構造化 JSON（`GroundedState` / `payload_hash`）として伝達せよ。
        
3. **Do Not Fabricate (存在しない実体を偽造するな)**:
    
    - 実データや根拠が欠落している場合、推定値で埋めずに明確に `null` または `BLOCKED` として報告せよ。
        
4. **Preserve Category Universality (圏の整合性を維持せよ)**:
    
    - 知識の追加・変更を行う際は、既存の概念・関係性の可換性を破綻させないか（矛盾を発生させないか）を代数的に検証せよ。
        

[ SPEC END: SPEC-SENSOS-KNOWLEDGE-CORE-001 ]