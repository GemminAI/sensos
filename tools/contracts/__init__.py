"""Reference implementation of the IC-00 contract primitives (IC-00 1.0.0, design v0.7.1).

Standard library + jsonschema only; imports nothing from sensos or any other
repository. The language-neutral vectors under
docs/architecture/contracts/common/vectors/ are the portable definition; this
package is one implementation that must pass them.
"""

from __future__ import annotations

from contracts.check import Violation, check_envelope
from contracts.errors import ContractError
from contracts.ids import (
    artifact_id,
    content_id,
    observation_id,
    session_id_experiment,
    session_id_operational,
)
from contracts.jcs import jcs
from contracts.quantize import dequantize, quantize
from contracts.strict_load import strict_load

__all__ = [
    "ContractError",
    "Violation",
    "artifact_id",
    "check_envelope",
    "content_id",
    "dequantize",
    "jcs",
    "observation_id",
    "quantize",
    "session_id_experiment",
    "session_id_operational",
    "strict_load",
]
