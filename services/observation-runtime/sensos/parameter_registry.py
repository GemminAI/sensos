"""
sensos.parameter_registry — SPEC-SENSOS-RTV2-001 v1.4 §7.1 Parameter Registry
================================================================================

Single source of truth for the eight statistical/threshold constants frozen
by SPEC-SENSOS-RTV2-001 v1.4 §7.1. Per the spec: these must not be left as
magic numbers scattered through the code, and must be centralized as a
versioned registry.

No component in this repository consumes these values yet — DAK phase
detection (Crystal/Glass/Plasma/Resonant, v1.4 §2.2), AEC (§5.3), and TCK-v2
G0-B/G1/G2 (§7.4) are themselves not yet implemented. This module exists so
that when those consumers are built, they read from here rather than
re-introducing scattered magic numbers (as already happened once in this
repo — see ``sa002_trajectory``/``exp7500``-style bare ``threshold: float``
defaults elsewhere in this codebase).

A human-readable copy of these values lives in
``configs/parameter_registry.yaml`` at the repo root, alongside the existing
``configs/dak.yaml`` / ``configs/auth.yaml``. That YAML file is NOT loaded at
container runtime — this service's Docker build context
(``services/observation-runtime``) does not COPY the repo-root ``configs/``
directory into the image (only ``sensos/`` and ``pyproject.toml``/
``README.md`` are copied). This is the same reason ``configs/dak.yaml`` is
already orphaned in production. The dataclass defaults below are therefore
the actual, working single source of truth at runtime; the YAML is a
reference copy whose consistency with this module is enforced by the repo
root's ``tests/test_parameter_registry.py`` (run with
``PYTHONPATH=services/observation-runtime``, matching this repo's existing
test convention — see ``tests/test_dak_kernel.py``), not assumed.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any

SPEC_ID = "SPEC-SENSOS-RTV2-001"
SPEC_REVISION = "v1.4"


@dataclass(frozen=True)
class ParameterRegistry:
    """The eight frozen constants from v1.4 §7.1, transcribed verbatim."""

    AEC_THRESHOLD_V1: float = 0.90
    CROSS_HARDWARE_EPSILON: float = 1e-4
    MIN_EFFECT_SIZE_DELTA: float = 0.05
    FDR_BENJAMINI_HOCHBERG_Q: float = 0.05
    CRYSTAL_VAR_EPSILON: float = 0.01
    CRYSTAL_ENTROPY_EPSILON: float = 0.05
    PLASMA_ENTROPY_DELTA: float = 0.05
    PLASMA_VAR_MAX: float = 10.0

    @classmethod
    def from_yaml(cls, path: str | Path) -> ParameterRegistry:
        """
        Validate a parameter_registry.yaml against the frozen v1.4 values
        and return the canonical registry.

        This is a validate-then-return-canonical operation, not a
        parse-and-trust one: the registry is a frozen standard (v1.4 §7.1
        forbids adding or changing these values), not a per-deployment
        tunable, so any missing key, extra key, or value that diverges from
        the frozen spec raises rather than silently loading a divergent
        registry.
        """
        import yaml

        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"parameter_registry.yaml not found at {p}")

        with open(p, "r", encoding="utf-8") as fh:
            raw: dict[str, Any] = yaml.safe_load(fh) or {}

        block = raw.get("parameter_registry")
        if block is None:
            raise ValueError(f"{p}: missing top-level 'parameter_registry' key")

        default = cls()
        expected = {f.name: getattr(default, f.name) for f in fields(cls)}

        missing = expected.keys() - block.keys()
        extra = block.keys() - expected.keys()
        if missing:
            raise ValueError(f"{p}: missing required keys: {sorted(missing)}")
        if extra:
            raise ValueError(f"{p}: unexpected keys not in v1.4 §7.1: {sorted(extra)}")

        mismatched = {
            k: (block[k], expected[k])
            for k in expected
            if float(block[k]) != float(expected[k])
        }
        if mismatched:
            raise ValueError(
                f"{p}: values diverge from frozen v1.4 §7.1 spec: {mismatched}"
            )

        return default


DEFAULT = ParameterRegistry()
