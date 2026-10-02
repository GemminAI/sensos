#!/usr/bin/env bash
# SensOS Linux installer.
#
# Real, previously-verified reference for the vLLM/CUDA path: see
# docs/handoff/HANDOFF_SA001_RUNPOD_BASELINE.md ("pip install vllm";
# "vllm serve <model> --port 8000 --dtype auto --gpu-memory-utilization
# 0.85 --max-model-len 4096"). This script installs the SensOS Runtime,
# Semantic Annotator, and vLLM -- it does not start a vLLM server or
# pick a model for you: run `vllm serve <model>` yourself, then point
# `sensos smoke` at it via RUNTIME_BRIDGE_URL / SENSOS_MODEL_ID.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "== SensOS Linux installer =="
echo

os="$(uname -s)"
if [ "$os" != "Linux" ]; then
  echo "FAIL: this installer targets Linux (detected: $os)"
  exit 1
fi
echo "OS: Linux ($(uname -m))"

if ! command -v python3 >/dev/null 2>&1; then
  echo "FAIL: python3 not found on PATH"
  exit 1
fi
python_version="$(python3 -c 'import sys; print("%d.%d.%d" % sys.version_info[:3])')"
echo "Python: $python_version"
if ! python3 -c 'import sys; sys.exit(0 if sys.version_info[:2] >= (3, 12) else 1)'; then
  echo "FAIL: Python >=3.12 required (found $python_version)"
  exit 1
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "FAIL: uv not found on PATH."
  echo "Install it, then re-run this script:"
  echo "    curl -LsSf https://astral.sh/uv/install.sh | sh"
  exit 1
fi
echo "uv: $(uv --version)"
echo

echo "-- Installing SensOS Runtime + Semantic Annotator (uv sync) --"
uv sync
echo

echo "-- Installing Linux inference backend (vLLM) --"
uv pip install vllm
echo

echo "-- Running 'sensos doctor' --"
set +e
uv run sensos doctor
doctor_status=$?
set -e
echo

if [ "$doctor_status" -eq 0 ]; then
  echo "Install complete."
else
  echo "Install complete, but 'sensos doctor' reported failures above (see output)."
fi
echo "Next steps:"
echo "  1. Start a vLLM server, e.g.:"
echo "       uv run vllm serve <model> --port 8000 --dtype auto"
echo "  2. export RUNTIME_BRIDGE_URL=http://localhost:8000"
echo "  3. export SENSOS_MODEL_ID=<model>"
echo "  4. uv run sensos smoke"

exit "$doctor_status"
