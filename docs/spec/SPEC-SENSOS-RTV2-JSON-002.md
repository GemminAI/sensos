# SensOS Runtime v2.0 — Canonical JSON / JCS Wire Protocol Specification

**Document ID**: SPEC-SENSOS-RTV2-JSON-002

**Status**: Architecture Protocol Specification (Final Draft / V2 Constitution Enforced)

**Standard Compliance**: RFC 8785 (JSON Canonicalization Scheme / JCS), SHA-256 Deterministic Identity Hashing

## 1. Executive Summary & V2 Protocol Constitution

SensOS Runtime v2.0 では、サブシステム間の通信境界（Runtime API Boundaries）における不透明な暗黙的データ受け渡しを廃止し、RFC 8785 (JCS) に準拠した正規化 JSON を決定論的データ交換フォーマットとして導入する。

### 1.1 V2 Constitution (Three Core Rules)

1. **Rule 1 — Wire First (Standardize the Wire, Not Unverified Semantics)**:
    
    > _"プロトコルは通信境界（Wire）を標準化するものであり、未実証の内部意味論（Unverified Internal Semantics）を事前規定してはならない。"_
    > 
    > 本仕様は共通メッセージエンベロープ（Envelope）と決定論的ハッシュ方式のみを強制し、個々の 38 Ports やモデル内部のデータ構造（Payload）はワイヤーレベルで実測・確認された後にのみ能力定義を固定する。
    
2. **Rule 2 — Evidence Promotion**:
    
    > _"PROPOSED ステータスから VERIFIED ステータスへの昇格は、以下のパイプライン順序を厳格に経たもののみに許可される。"_
    > 
    > $$> \text{SPEC} \longrightarrow \text{CODE} \longrightarrow \text{CONFIG} \longrightarrow \text{LIVE ENDPOINT} \longrightarrow \text{WIRE TRACE} \longrightarrow \text{TCK} >$$
    
3. **Rule 3 — Capability Discovery**:
    
    > _"38 Ports は削減せずフルセットを維持・保護する。各ポートの意味論・能力はワイヤーレベルのログ実測（Evidence）を通じて個別に発見・登録される。"_
    > 
    > 8 Port 圧縮を初期設計目標とせず、38 Ports の多重 Capability（観測・帰属・介入・制御）を実測により確定させる。
    

### 1.2 Scope Limitation

本規格が適用されるのは Runtime API 境界（CLE $\leftrightarrow$ NVS $\leftrightarrow$ GPT-OSS $\leftrightarrow$ 38 Ports $\leftrightarrow$ DAK $\leftrightarrow$ HEKB）であり、モデル内部処理におけるテンソル表現（例: GPT-OSS 隠れ状態の Float Tensor や NVS 内部配列等）の内部フォーマットを拘束しない。

## 2. Two-Layer Protocol Architecture

データ構造は「共通プロトコルエンベロープ（Protocol Envelope）」と「ポート固有能力ペイロード（Capability Payload）」の2層に厳密に分離する。現在定義されている実行パスはワイヤー実測前の仮説段階（Candidate Path）であり、実証ログの収集を経て昇格（Verified Path）する。

```
 [ Candidate V2 Runtime Path (To be VERIFIED via Wire Trace) ]

 ┌────────────────────────────────────────────────────────────────────────┐
 │ Common Protocol Envelope                                               │
 │ - contract_version: "2.0.0"                                            │
 │ - message_type: "PORT_EXECUTION_REQUEST" / "PORT_EXECUTION_RESPONSE"  │
 │ - event: { session_id, timestamp_utc, ... }                           │
 │ - payload: { port_id, input / output ... }                            │
 │ - payload_hash: SHA256(JCS(payload))                                  │
 └──────────────────────────────────┬─────────────────────────────────────┘
                                    │
                                    ▼
 ┌────────────────────────────────────────────────────────────────────────┐
 │ Port-Specific Capability Payload (Discovered & Registered per Port)   │
 │ ├── P01 ... P11 : Sub-Lexical / Polysemy Payloads                      │
 │ ├── P12 ... P22 : Reframing / Temporal Payloads                        │
 │ └── P23 ... P38 : Boundary / System Control Payloads                   │
 └────────────────────────────────────────────────────────────────────────┘
```

## 3. Schema Specifications

### 3.1 Common Protocol Request Envelope (`POST /v2/ports/{port_id}/execute`)

全 38 Ports への実行要求は、以下の共通エンベロープ構造に準拠する。

```
{
  "contract_version": "2.0.0",
  "message_type": "PORT_EXECUTION_REQUEST",
  "event": {
    "session_id": "rtv2-sess-20260814-0891",
    "timestamp_utc": "2026-08-14T16:51:14Z",
    "sequence_index": 2
  },
  "payload": {
    "port_id": "P17_COUNTERFACTUAL_REFRAMING",
    "capability_version": "1.0.0",
    "input_context": {
      "cle_grounded_state": {
        "five_w1h": {
          "who": "Italian Elderly",
          "to_whom": "Japanese Tourist",
          "reference": "Germany",
          "when": "Future_Counterfactual",
          "where": "Rome_Street",
          "action": "Exclude_Alliance"
        },
        "sok": "HISTORICAL_REFRAMING_JOKE",
        "representation": {
          "type": "UNSPECIFIED",
          "vector": [0.0124, -0.8421, 0.3112, 0.0519]
        }
      },
      "nvs_kinematics": {
        "step_index": 2,
        "curvature": 1.5582,
        "velocity_norm": 1.4142
      }
    }
  },
  "payload_hash": "a591a6d40bf420404a011733cfb7b190d62c65bf0bcda32b57b277d9ad9f146e"
}
```

### 3.2 Common Protocol Response Envelope

ポートからの返却レスポンスも同様にエンベロープでラップし、時刻非依存な `payload_hash` を保持する。

```
{
  "contract_version": "2.0.0",
  "message_type": "PORT_EXECUTION_RESPONSE",
  "event": {
    "session_id": "rtv2-sess-20260814-0891",
    "execution_timestamp_utc": "2026-08-14T16:51:14.050Z",
    "status": "SUCCESS"
  },
  "payload": {
    "port_id": "P17_COUNTERFACTUAL_REFRAMING",
    "raw_port_observation": {
      "delta_curvature": 1.412,
      "port_active_flag": true
    },
    "intervention_candidate": {
      "suggested_action": "INJECT_CONTRADICTION_DAMPING",
      "target_layer_range": [12, 24]
    }
  },
  "payload_hash": "7f83b1657ff1fc53b92dc18148a1d65dfc2d4b1fa3d677284addd200126d9069"
}
```

## 4. Deterministic Hash Hierarchy: Separation of Payload Identity and Event Identity

同一の意味的入力（`payload`）と実行コンテキスト（`event`）を明確に識別するため、ハッシュ計算を二層化する。

1. **Semantic Payload Hash (`payload_hash`)**:
    
    `payload` オブジェクトのみを JCS 正規化して算出した SHA-256。タイムスタンプ等に依存せず、「同一の意味的入力・出力か」を判定する同一性識別子（Semantic Identity）。
    
    $$\text{payload\_hash} = \text{SHA256}\Big(\text{JCS}(\text{payload})\Big)$$
2. **Event Sequence Hash (`event_hash`)**:
    
    セッションID、タイムスタンプ、シーケンス番号および `payload_hash` を結合して算出する時系列監査識別子（Event Identity）。
    
    $$\text{event\_hash} = \text{SHA256}\Big(\text{JCS}(\{\text{event},\, \text{payload\_hash}\})\Big)$$

## 5. CLE (Categorical Lift Engine) Interface Schema

CLE（Categorical Lift Engine）における `/ground` エンドポイントからの出力は、未検証の埋め込みモデル名を前もって仮定せず、`representation.type` を実測・確定前は `UNSPECIFIED` と規定する。

```
{
  "cle_version": "2.0.0",
  "grounded_state": {
    "five_w1h": {
      "subject": "Italian Elderly",
      "recipient": "Japanese Tourist",
      "reference_entity": "Germany",
      "temporal_frame": "Future_Counterfactual",
      "location_context": "Rome_Street",
      "action_core": "Exclude_Alliance"
    },
    "sok": "HISTORICAL_REFRAMING",
    "representation": {
      "type": "UNSPECIFIED",
      "vector": [0.0124, -0.8421, 0.3112, 0.0519]
    }
  }
}
```

## 6. End-to-End Auditable JSON Trace & Directives for TCK-v2

1. **Strict Envelope Validation**:
    
    全 API エンドポイントにおいて、`contract_version` および `payload_hash` の不一致を含む JSON リクエストは HTTP 422 で棄却する。
    
2. **JCS Hash Self-Verification**:
    
    受信側は受け取った `payload` に対し $\text{SHA256}(\text{JCS}(\text{payload}))$ を再計算し、レスポンスに付与された `payload_hash` との一致を検証する。
    
3. **Incremental Capability Discovery**:
    
    38 Ports それぞれの固有フィールド（`payload` 内部構造）は、TCK-v2 によるワイヤーレベルの応答監査で実測・確認されたものから順次スキーマ登録を行う。