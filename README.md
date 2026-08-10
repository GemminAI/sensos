**

# SensOS Runtime v1.0

SensOS Runtime is a next-generation distributed AI operating runtime that dynamically connects and integrates normalized knowledge bases (such as HEKBv2), mathematical cores, and local inference engines (MLX/CUDA/CPU) via MCP (Model Context Protocol).

## 💡 What is SensOS?

SensOS is an inter-AI runtime middleware that enables seamless interaction between AI agents (e.g., Claude Code, Cursor, custom agents) and structured backend knowledge assets (mathematical models, normalized RFCs, and knowledge bases).

### Key Features

1. MCP (Model Context Protocol) Native
    

- Knowledge bases and computational cores are exposed as MCP Servers, allowing multiple AI agents to concurrently query and operate on them.
    

2. Distributed Knowledge & Inference Hybrid
    

- Seamlessly bridges Linux-hosted normalized knowledge (such as HEKBv2) with Apple Silicon (MLX) or GPU-accelerated inference infrastructure.
    

3. Context Collapse Prevention
    

- Prevents LLM context overflow by providing structured tools and resources for on-demand knowledge access rather than dumping massive raw text directly into prompt windows.
    

## 🏗 System Architecture

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
        Inference["Inference Engine<br/>(MLX / vLLM / PyTorch)"]  
        Knowledge["HEKBv2 Knowledge<br/>(Normalized RFCs / Math Cores)"]  
    end  
  
    Clients <-->|MCP Protocol / stdio / SSE| Core  
    Core <--> Inference  
    Core <--> Knowledge  
  

## 🚀 Quick Start for Clean Linux Environments

Follow these steps to set up and initialize SensOS Runtime on a clean Linux installation (e.g., Ubuntu 22.04 LTS / 24.04 LTS).

### 1. Install System Dependencies

Install required build tools, Git, and Python development utilities:

sudo apt update && sudo apt install -y \  
    git \  
    python3 \  
    python3-pip \  
    python3-venv \  
    build-essential \  
    curl  
  

### 2. Clone the Repository

git clone https://github.com/GemminAI/sensos.git  
cd sensos  
  

### 3. Set Up Python Virtual Environment

Create an isolated virtual environment to avoid polluting global system packages:

python3 -m venv .venv  
source .venv/bin/activate  
  

### 4. Install Dependencies

pip install --upgrade pip setuptools wheel  
pip install -r requirements.txt  
  

(Optional: Install in editable mode)

pip install -e .  
  

### 5. Verification & Diagnostics

Verify the installation using the SensOS CLI diagnostic command:

# Check version  
sensos --version  
  
# Run system diagnostics (verifies Python environment, dependencies, and MCP interface)  
sensos doctor  
  

## ⚙️ Knowledge Base (HEKBv2) & MCP Integration

### 1. Configure MCP File

Create an mcp_config.json file in the root directory to define target knowledge bases and tools:

{  
  "mcpServers": {  
    "hekb-core": {  
      "command": "python3",  
      "args": [  
        "-m", "sensos.mcp.hekb_server",  
        "--kb-path", "/path/to/HEKBv2/knowledge_base"  
      ]  
    }  
  }  
}  
  

### 2. Run Connectivity Test

sensos mcp test --config mcp_config.json  
  

## 🤝 AI Agent Integration (Claude Code / Cursor)

To connect SensOS to your development agents, point the agent's MCP settings to mcp_config.json:

- For Claude Code:  
    claude --mcp-config mcp_config.json  
      
    
- For Cursor: Navigate to Settings > Features > MCP and register the server definition from mcp_config.json.
    

## 📄 License

[MIT License](http://docs.google.com/LICENSE)

**
