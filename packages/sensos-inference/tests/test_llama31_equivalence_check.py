"""``llama31_equivalence_check`` is reachable from the Llama adapter (no model: the call is faked).

The comparison itself needs MLX and real weights; it is exercised in ``test_u2_real_machine.py``.
"""

from __future__ import annotations

from typing import Any

import sensos_inference.llama31_equivalence as equivalence
from sensos_inference.adapters import Llama31MLXAdapter


def test_adapter_check_equivalence_calls_the_function_with_its_provider(monkeypatch: Any) -> None:
    seen: dict[str, Any] = {}

    def fake(provider: Any, prompt_ids: Any, token_ids: Any, **options: Any) -> dict[str, Any]:
        seen.update(provider=provider, prompt=list(prompt_ids), tokens=list(token_ids), **options)
        return {"bit_identical": True}

    monkeypatch.setattr(equivalence, "llama31_equivalence_check", fake)
    provider = object()
    result = Llama31MLXAdapter(provider).check_equivalence([1, 2, 3], [4, 5], tail=16, steps=2)
    assert result == {"bit_identical": True}
    assert seen == {
        "provider": provider,
        "prompt": [1, 2, 3],
        "tokens": [4, 5],
        "tail": 16,
        "steps": 2,
    }


def test_the_function_is_exported() -> None:
    assert "llama31_equivalence_check" in equivalence.__all__
