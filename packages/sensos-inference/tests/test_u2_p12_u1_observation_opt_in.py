"""T-U2-P-12: optional re-run of the U1 observation suite (explicit opt-in only).

WARNING
-------
Running this test executes U1's real capture Provider path (``capture_chat`` with a fake
loader). That path still reaches ``import mlx.core`` inside ``_ensure_loaded`` and can
abort the process (SIGABRT / Metal init) under a restricted sandbox or a broken MLX
environment. It is **not** part of the normal U2 preparation suite.

Opt-in
------
Set ``U2_RUN_P12_U1_OBSERVATION=1`` (exact value ``1``) before invoking this file, e.g.::

    U2_RUN_P12_U1_OBSERVATION=1 python3 -m pytest -q tests/test_u2_p12_u1_observation_opt_in.py

Without the opt-in, the single test below is skipped. Do not collect this file as part of
routine Adapter prep (``tests/test_adapters.py``).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

# Exact opt-in flag. Any other value (or unset) keeps P-12 skipped.
ENV_RUN_P12 = "U2_RUN_P12_U1_OBSERVATION"


def _p12_opt_in() -> bool:
    return os.environ.get(ENV_RUN_P12) == "1"


@pytest.mark.skipif(
    not _p12_opt_in(),
    reason=f"{ENV_RUN_P12}=1 required (runs U1 Providers; may import mlx.core)",
)
def test_t_u2_p_12_u1_observation_suite_still_passes_may_import_mlx_core() -> None:
    """Re-run U1's observation suite in a subprocess (unchanged files; expect 83 passed).

    Explicit-opt-in only. Reaches U1 real Provider ``capture_chat`` and may ``import mlx.core``
    even after a fake loader. A sandbox that aborts Metal init is an environment limit, not
    an Adapter regression.
    """
    import re
    import subprocess
    import sys

    observation = Path(__file__).with_name("test_observation.py")
    # Prefer a Python without MLX when available: U1 observation tests only need numpy.
    candidates = [sys.executable, "python3"]
    last_out = ""
    for exe in candidates:
        env = dict(os.environ)
        env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
        # Avoid picking up an editable install that pulls MLX during provider import side paths.
        env.pop("VIRTUAL_ENV", None)
        proc = subprocess.run(
            [exe, "-m", "pytest", "-q", str(observation)],
            cwd=str(Path(__file__).resolve().parents[1]),
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        last_out = proc.stdout + proc.stderr
        if proc.returncode == 0:
            matched = re.search(r"(\d+) passed", proc.stdout)
            assert matched is not None
            assert int(matched.group(1)) >= 83
            return
        if "Fatal Python error" in last_out or "Aborted" in last_out:
            continue
        assert proc.returncode == 0, last_out
    pytest.fail(f"U1 observation suite did not pass on any candidate interpreter:\n{last_out}")
