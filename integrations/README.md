# Integrations

SensOS-side adapters to external OSS / protocols.

| Path | Role |
|------|------|
| `hekb-projection/` | Product-facing HEKB projection service (not HEKB core) |
| `hekb-mcp/` | MCP tools that talk to HEKB |

## Rules

- HEKB / HEXT implementations stay upstream
- Adapters may wrap HTTP / MCP / config only
- No research experiment reports under this tree
