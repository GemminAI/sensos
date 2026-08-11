# SensOS

> **Status: Documentation-only repository**
>
> The current repository contains only a project description (this README).
> It does not currently include a runnable SensOS implementation — there is
> no source code, no installable package, no CLI, and no dependency manifest
> in this repository yet.

## A. What this repository currently contains

As of the current `empty` branch (the repository's default branch), cloning
this repository gives you exactly one file:

```text
README.md
```

There is no `pyproject.toml`, `setup.py`, `requirements.txt`, `src/`,
`sensos/`, `tests/`, `mcp_config.json`, or `LICENSE` file in this
repository. No `sensos` CLI, MCP server, or MLX/inference integration code
is present.

## What is SensOS (project description)

SensOS is described as a next-generation distributed AI operating runtime
intended to dynamically connect and integrate normalized knowledge bases
(such as HEKBv2), mathematical cores, and local inference engines
(MLX/CUDA/CPU) via the Model Context Protocol (MCP).

The intent is for SensOS to act as inter-AI runtime middleware, enabling AI
agents (e.g., Claude Code, Cursor, custom agents) to interact with
structured backend knowledge assets — mathematical models, normalized RFCs,
and knowledge bases.

**Intended key features (not yet implemented in this repository):**

- **MCP-native** — knowledge bases and computational cores exposed as MCP
  servers, queryable by multiple AI agents concurrently.
- **Distributed knowledge & inference hybrid** — bridging normalized
  knowledge (such as HEKBv2) with Apple Silicon (MLX) or GPU-accelerated
  inference infrastructure.
- **Context collapse prevention** — structured, on-demand knowledge access
  instead of dumping raw text into prompt windows.

These are design goals for the project, not capabilities available in the
current repository.

## B. What you can do today

```bash
git clone https://github.com/GemminAI/sensos.git
cd sensos
ls
```

At this point you will see `README.md` and nothing else. There is no
further installation, build, or run step that will currently succeed —
this document is the extent of what is available.

## C. What is not yet available

The following do **not** exist in this repository yet:

- Any Python package, module, or source code (`sensos/`, `src/`)
- A dependency manifest (`requirements.txt`, `pyproject.toml`)
- A `sensos` CLI or any executable entry point
- An MCP server implementation or `mcp_config.json` example that
  corresponds to real code
- MLX, vLLM, or PyTorch integration code
- HEKB / HEKBv2 integration code
- Tests
- A `LICENSE` file (license terms are therefore undetermined at this time)

If your goal is to install and run SensOS, that is not yet possible from
this repository. Check back for updates, or refer to the project's other
repositories under the GemminAI organization for related, independently
maintained components.

## Planned / Target architecture

The diagram below describes the **intended future architecture** of
SensOS. None of the components shown are implemented in this repository
today; this section exists to communicate project direction only.

```text
Planned / Target architecture (not implemented in this repository)

flowchart TD
    subgraph Clients["AI Clients / Agents"]
        Claude["Claude Code"]
        Cursor["Cursor"]
        Agent["SensOS Agent"]
    end

    subgraph Core["SensOS Runtime Core"]
        Orchestrator["Task Orchestrator"]
        Abstraction["Model Abstraction Layer"]
        MCPClient["MCP Client / Hub"]
        Optimizer["Context Optimization"]
    end

    subgraph Infrastructure["Backend Resources"]
        Inference["Inference Engine (MLX / vLLM / PyTorch)"]
        Knowledge["HEKBv2 Knowledge (Normalized RFCs / Math Cores)"]
    end

    Clients <-->|MCP Protocol / stdio / SSE| Core
    Core <--> Inference
    Core <--> Knowledge
```

## MLX

MLX support / runtime integration is not included in the current
repository state. No MLX installation steps, provider code, model
loading, or inference examples exist here. MLX-related verification for
Apple Silicon hardware, where it exists, is tracked in a separate,
independent repository and is out of scope for this document.

## License

No `LICENSE` file is currently present in this repository. License terms
are therefore undetermined until one is added.
