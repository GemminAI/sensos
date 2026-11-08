from __future__ import annotations

import sys
from pathlib import Path

_TOOLS = Path(__file__).resolve().parents[2] / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))
sys.path.insert(0, str(_TOOLS / "contracts"))  # make_vectors is a script next to the package
