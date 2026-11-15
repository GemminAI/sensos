"""U2 real-machine test skeleton (T-U2-R-*).

Real-model cases are skipped unless ``LLAMA31_SNAPSHOT`` / ``QWEN35_SNAPSHOT`` name a local
snapshot directory. Collection must not import ``mlx`` or load weights. U2-3 / U2-4 fill bodies.
"""

from __future__ import annotations

import os

import pytest
from u2_support import (
    DEFAULT_NOT_VERIFIED,
    ENV_LLAMA,
    ENV_QWEN,
    FIXED_PROMPTS,
    llama_real_machine_available,
    qwen_real_machine_available,
)


def test_u2_fixed_prompt_set_and_not_verified_defaults() -> None:
    """Always runs: defines the fixed prompt ids and the mandatory not_verified baseline."""
    assert set(FIXED_PROMPTS) >= {"p01", "p02", "p03", "p04"}
    assert len(DEFAULT_NOT_VERIFIED) >= 1


@pytest.mark.skipif(not llama_real_machine_available(), reason=f"{ENV_LLAMA} not set")
def test_t_u2_r_llama_placeholder_requires_snapshot() -> None:
    """U2-4 will implement AC-B/C checks. This placeholder only proves the skip gate."""
    path = os.environ[ENV_LLAMA]
    assert path.strip()
    pytest.skip("U2-4 real-machine body not implemented in U2-1/U2-2")


@pytest.mark.skipif(not qwen_real_machine_available(), reason=f"{ENV_QWEN} not set")
def test_t_u2_r_qwen_placeholder_requires_snapshot() -> None:
    """U2-3 will implement AC-B/C checks. This placeholder only proves the skip gate."""
    path = os.environ[ENV_QWEN]
    assert path.strip()
    pytest.skip("U2-3 real-machine body not implemented in U2-1/U2-2")
