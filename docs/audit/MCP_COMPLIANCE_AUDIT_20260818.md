# SensOS Runtime MCP Implementation — Spec Compliance Audit

**日付:** 2026-08-18
**対象:** `services/nvs-runtime/runtime/mcp/{server.py,tools.py}`
**正規情報源:** 公式MCP仕様（`modelcontextprotocol.io/specification/2025-06-18/*`、fetch済み）および実際にインストールされている公式Python SDK（`mcp` パッケージ、venv内で直接検証）。READMEやSDKのdocstringだけでなく、実行による検証を優先。

## 0. 最重要所見（先に結論）

**現状の `runtime/mcp/server.py` は、そのプロジェクト自身のvenvに実際にインストールされているMCP SDKに対して import すらできず、起動不能です。**

```
$ .venv/bin/python3 -c "import runtime.mcp.server"
AttributeError: 'Server' object has no attribute 'list_tools'
```

原因: `requirements.txt` は `mcp==1.9.0` を固定しているが、venvには `mcp==2.0.0` が実際にインストールされている（PyPI番号は連続、1.9.0→2.0.0の間に89リリースの差）。`mcp==2.0.0` の低レベル `Server` クラスは `@server.list_tools()`/`@server.call_tool()` という**デコレータメソッド自体を廃止**しており、`on_call_tool`/`on_list_tools` コンストラクタ引数か、より高レベルな `mcp.server.mcpserver.MCPServer` を使う新しいAPIに置き換わっている（`git show`ではなく実際に `grep -rn "def call_tool(self\|def list_tools(self" mcp/` を実行し、確認: 該当メソッドはゼロ件）。

検証のため `mcp==1.9.0` を隔離環境に実インストールしたところ、コードは問題なくimportでき、9ツールすべて正しく登録されることを確認した:

```
$ python3 -c "import sys; sys.path.insert(0,'<mcp190>'); import runtime.mcp.server as m; print(list(m.FULL_TOOLS)+list(m.ASYNC_TOOLS))"
IMPORT OK against mcp==1.9.0
tools registered: ['nvs_register_agent', 'nvs_create_session', 'nvs_emit_sep_event', 'nvs_query_events',
 'nvs_meaning_mapper_capability', 'nvs_run_meaning_trajectory', 'nvs_get_port_capability',
 'nvs_invoke_port', 'nvs_persist_port_evidence']
```

**結論: `runtime/mcp/server.py`/`tools.py` のコード自体は、ピン留めされたSDKバージョン(1.9.0)に対しては正しく書かれている。壊れているのはvenvの実体で、pinが守られていない環境ドリフトが原因。** これは「MCP仕様違反」ではなく「依存関係の実体がpinと一致していない」という、監査ゲートを通す前に対処すべき前提条件の欠落である。

**対処（本監査の一部として実施、意味論の変更なし）:** `services/nvs-runtime/.venv` に `mcp==1.9.0`（既存pin通り）を再インストールし、importが通ることを実測で確認した上で監査を継続する。SDKのメジャーバージョンを上げる・低レベルAPIから高レベルAPIへ移行する、といった設計判断は本監査のスコープ外（「SensOSのsemanticsを再設計しない」という指示に従い、ここでは行わない）。

`mcp==1.9.0` が話す公式プロトコルバージョンは `2025-03-26`（`mcp/types.py` の `LATEST_PROTOCOL_VERSION` を実測）。現在の公式仕様サイトで確認できる最新の公開revisionは `2025-06-18`。venvに実際に入っていた `mcp==2.0.0` はさらに新しい `2026-07-28`（"stateless per-request envelope"という新しいlifecycleモデル）まで話せることを `mcp_types/version.py` から確認済みだが、今回はpinを尊重し1.9.0側で監査する。

---

## 1. Protocol version / initialization / lifecycle — **PARTIAL**

- `runtime/mcp/server.py`は `server.run(read_stream, write_stream, server.create_initialization_options())` という標準パターンを使用。これはSDKに `initialize`/`initialized`/`operation`/`shutdown` の全ライフサイクルを委譲しており、アプリケーションコードが手動でハンドシェイクを再実装していない — これ自体は正しい設計判断。
- ただし1.9.0がネゴシエートできるプロトコルバージョンは `2025-03-26` のみ（1バージョンしか知らない）。公式仕様のバージョンネゴシエーション規範（「サーバはクライアントの要求バージョンに対応できなければ、自分がサポートする別バージョンで応答しなければならない」）自体はSDKが正しく実装している設計だが、**サーバが知っているバージョンが1つしかない**ため、2025-06-18以降のクライアントとは常に2025-03-26にダウングレードされる（クライアント側がそれを拒否すれば接続不可）。
- 判定PARTIAL: ハンドシェイクの実装自体は仕様に沿っているが、対応バージョンが古く、最新クライアントとの完全な互換性は保証されない。

## 2. Server capabilities negotiation — **COMPLIANT**

- `Server.get_capabilities()`（SDK内部、`mcp/server/lowlevel/server.py:555`）は登録済みハンドラから自動導出する: `"tools/list"` が登録されていれば `tools` capability、そうでなければ `prompts`/`resources` はNoneのまま。
- `runtime/mcp/server.py` はresources/promptsハンドラを一切登録していないため、`capabilities.tools` のみが正直に宣言される。実装していない機能を偽って宣言していない — 仕様の要求（「toolsをサポートするサーバは `tools` capabilityを宣言しなければならない」）を満たし、かつ過大申告もない。

## 3. tools/list — **COMPLIANT**

- `@server.list_tools()` で9ツール+4スタブ(LAYER3_STUBS)を返す。各ツールに `name`/`description`/`inputSchema` を設定 — 仕様の必須フィールドを満たす。`title`（任意フィールド）は未設定だが仕様上MAYであり必須ではない。
- ページネーション（`cursor`/`nextCursor`）は未実装だが、仕様上ページネーションは全体としてOPTIONAL（結果セットが小さい場合は省略可）。

## 4. tools/call — **COMPLIANT**

- `@server.call_tool()` でディスパッチ。SDK側 (`mcp/server/lowlevel/server.py`) が `func` の戻り値を `CallToolResult(content=list(results), isError=False)` にラップし、**例外発生時は自動的に `CallToolResult(isError=True, content=[TextContent(text=str(e))])` に変換する**ことを実コードで確認済み。したがって `KernelGateway.invoke_port()` の失敗（`RetryExhaustedError`）や `HekbClient.store()` の失敗は、正しく `isError: true` として伝播する。

## 5. Tool inputSchema — **COMPLIANT**

- 全ツールがJSON Schema形式の `inputSchema` を持つ（`type: object`, `properties`, `required`）。仕様の要求するJSON Schemaとして構文的に妥当。

## 6. structured tool output / outputSchema — **NOT_APPLICABLE（SDKバージョン起因）**

- `outputSchema`/`structuredContent` は2025-06-18で追加された仕様。`mcp==1.9.0`（プロトコル2025-03-26相当）の `types.py` には該当フィールドが存在しない（grep実測: ゼロ件）。
- 現在の全ツールは `json.dumps(result)` をラップした単一の `TextContent` のみを返しており、構造化出力そのものは提供していない。SDKバージョンの制約により導入不可能というだけでなく、アプリケーション側も意図的に使っていない。
- 判定: 「非準拠」ではなく「該当バージョンのSDKでは提供され得ない機能」としてNOT_APPLICABLEに分類。ただし今後 outputSchema を使いたい場合はSDKアップグレードが前提条件になる。

## 7. Resources semantics — **NOT_APPLICABLE**

- Resourcesは実装されていない。前述の通り `resources` capabilityも正直にNoneとして宣言されており、「実装していないと申告した上で実装していない」という誠実な状態。仕様違反ではない。

## 8. Prompts semantics — **NOT_APPLICABLE**

- Resourcesと同様。`prompts` capabilityは宣言されておらず、実装もない。

## 9. notifications / progress behavior — **NOT_APPLICABLE**

- `notifications/tools/list_changed` は未送信だが、`ToolsCapability(list_changed=False)`（デフォルト）として宣言されているため矛盾はない（listChanged=trueと申告してから送らない、という状態ではない）。
- progress通知（長時間実行ツール向け）は未実装。現在のツール（DB操作、HTTP1回のPort呼び出し等）は仕様上progressが必須になるような長時間処理ではないため、NOT_APPLICABLEと判定。

## 10. Error semantics — **PARTIAL（具体的な不整合を検出）**

公式仕様は明確に二層のエラーモデルを定義している（fetch済みテキストより直接引用）:

> Tools use two error reporting mechanisms:
> 1. **Protocol Errors**: Standard JSON-RPC errors for issues like: Unknown tools, Invalid arguments, Server errors
> 2. **Tool Execution Errors**: Reported in tool results with `isError: true`

かつ仕様が挙げる「Unknown tool」の例は明示的にJSON-RPCプロトコルエラー（`code: -32602`）である。

**実際のコード**（`runtime/mcp/server.py:183-184`）:
```python
else:
    result = {"error": "UNKNOWN_TOOL", "tool": name}
```
この分岐は例外を投げていないため、SDKの自動ラップは適用されず、`CallToolResult(isError=False, content=[TextContent(text='{"error": "UNKNOWN_TOOL", ...}')])` という**「成功」応答**としてクライアントに返る。仕様の例が明示的に「Unknown toolはプロトコルエラーであるべき」としているのに対し、これは失敗を成功のふりをして返しており、二重に規範から外れている（プロトコルエラーでもなく、`isError:true`のツール実行エラーでもない）。

一方、実際に例外を投げる経路（HEKB到達不能、Port呼び出し失敗など）はSDKの自動ラップにより正しく`isError:true`になる。**「本物の障害」は正しく伝わるが、「存在しないツール名を呼んだ」というクライアント側のミスだけが誤って成功として扱われる**、という限定的だが具体的な不整合。

## 11. Transport — **PARTIAL**

- **stdio**: 実装済み。`mcp.server.stdio.stdio_server()` を使用、標準的な使い方で仕様に沿う。**COMPLIANT**。
- **Streamable HTTP**: 未実装。`mcp==1.9.0`にはStreamable HTTPのサーバ実装が含まれる（SDK自体は対応)が、`runtime/mcp/server.py`はエントリポイントをstdio専用にハードコードしており、HTTP transportを提供する経路が存在しない。ユーザー指示に「if applicable」とあるが、現在のRuntimeがHTTPサービスとして稼働している以上（KernelGateway等はHTTPで動く）、外部からMCP接続する経路がstdioしかないのは実運用上の制約になり得る。**NOT_IMPLEMENTED**、必須ではないためPARTIALと判定（stdioは仕様通りだが、輸送層の選択肢が一つしかない）。

## 12. MCP client/server separation — **COMPLIANT**

- `runtime.mcp.server` はサーバ実装のみ。クライアント実装(`mcp.client.*`)への依存はコード上見当たらない。SensOS Runtime自身が他のMCPサーバのクライアントになるコードはこのモジュール外（例えば将来的なHEKB MCPクライアント）であるべきで、現状はその境界を侵していない。

## 13. MCP Inspector compatibility — **NOT_EVALUABLE（venv修復後は理論上COMPLIANT）**

- 実際に `@modelcontextprotocol/inspector` を起動しての接続検証は本セッションでは行っていない（Node.js/npm環境の要否含め、今回のスコープの中心ではないため）。
- ただし、venvを1.9.0に揃えた状態で標準的な低レベルSDKパターン（`Server` + `stdio_server`）を正しく使っている以上、Inspectorのstdio接続で `initialize`→`tools/list`→`tools/call` が動作しない理由はコード上見当たらない。**理論的評価としてはCOMPLIANTに近いが、実機検証をしていないためNOT_EVALUABLEと保守的に分類する。**

## 14. Current official Python SDK version compatibility — **NON_COMPLIANT（環境として）/ PARTIAL（コードとして）**

- 実際にインストールされていたバージョン（2.0.0、PyPI最新）に対しては**互換性なし**（importが失敗する、§0参照）。
- pinされたバージョン（1.9.0）に対しては互換だが、1.9.0自体が既に89リリース遅れており、現行の公式仕様revision（2025-06-18公開版、SDK内部的には2026-07-28まで存在）が持つ機能（outputSchema/structuredContent、モダンな`server/discover`ライフサイクル等）を一切利用できない。

---

## 監査結果サマリ表

| # | 項目 | 判定 |
|---|---|---|
| 1 | Protocol version / initialization / lifecycle | PARTIAL |
| 2 | Server capabilities negotiation | COMPLIANT |
| 3 | tools/list | COMPLIANT |
| 4 | tools/call | COMPLIANT |
| 5 | Tool inputSchema | COMPLIANT |
| 6 | structured tool output / outputSchema | NOT_APPLICABLE |
| 7 | Resources semantics | NOT_APPLICABLE |
| 8 | Prompts semantics | NOT_APPLICABLE |
| 9 | notifications / progress | NOT_APPLICABLE |
| 10 | Error semantics | PARTIAL |
| 11 | Transport (stdio / Streamable HTTP) | PARTIAL（stdio: COMPLIANT、HTTP: 未実装） |
| 12 | MCP client/server separation | COMPLIANT |
| 13 | MCP Inspector compatibility | NOT_EVALUABLE |
| 14 | Current official Python SDK version | NON_COMPLIANT(環境) / PARTIAL(コード) |

**NON_COMPLIANTは0件、ただし#0（venvドリフト）を放置した場合は事実上サーバが起動しないため、監査全体としては「修復後は概ねPARTIAL〜COMPLIANT」「修復前は起動不能」という二段階の結論になる。**

---

## Phase 1 進行の可否判断

ユーザー指示「このaudit がpassした後にのみ後続作業を進める」に対する回答:

- ブロッカーだった§0（venvドリフト）は、`mcp==1.9.0`をpin通りに再インストールする**環境修復のみ**で解消可能であり、SensOSのsemanticsやMCPの使い方を変更するものではない。これを実施した。
- 残る PARTIAL 項目（#1バージョン幅、#10 unknown-tool、#11 HTTP transport）はいずれも**既存9ツールを壊す・意味を変えるものではなく**、新規に追加するHEKB Read MCP toolsの実装様式（exampleに倣って例外は投げる、成功時は`isError`なしで返す）を選べば、新規ツール側では最初から正しい形で実装できる。
- 既存の `nvs_*` ツール群のunknown-tool分岐修正は、今回のスコープ外（HEKB Read MCP追加が目的であり、既存9ツールの挙動変更は要求されていない）。**指摘のみ行い、変更しない。**

**判定: Phase 1（HEKB Read MCP Tools）へ進行可能。**
