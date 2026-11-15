"""Entry for the payloads of the nvs contracts, beside ``gate.py`` (which is pinned by the IC-02 0.10.0 lock).

``check_nvs_payload`` has two kinds of return value:

* ``nvs.hidden-trajectory`` ``0.1.0``: ``check_hidden_trajectory`` and nothing else (``gate.check_payload`` is
  not called); the result is a ``HiddenTrajectoryResult`` (violations and UNVERIFIABLE).
* any other ``payload_schema``: ``gate.check_payload`` with the same arguments and its return value as it is
  (``list[Violation]``; an unknown id is ``S39``, as before).

Another version of ``nvs.hidden-trajectory`` (``0.2.0``, ``0.1.0-draft``) is ``S39``, in a
``HiddenTrajectoryResult``. ``gate.PAYLOAD_SCHEMAS`` is not extended.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from contracts import gate
from contracts.check import Violation
from contracts.hidden_trajectory import (
    PAYLOAD_SCHEMA_ID,
    PAYLOAD_SCHEMA_VERSION,
    HiddenTrajectoryResult,
    check_hidden_trajectory,
)


def check_nvs_payload(
    envelope: Mapping[str, Any],
    stored: Mapping[str, Any] | None = None,
    blobs: Mapping[str, bytes] | None = None,
    parent_contents: Mapping[str, str] | None = None,
) -> HiddenTrajectoryResult | list[Violation]:
    declared = envelope["payload_schema"]
    if declared["id"] == PAYLOAD_SCHEMA_ID:
        if declared["version"] != PAYLOAD_SCHEMA_VERSION:
            message = f"unknown payload_schema {declared['id']} {declared['version']}"
            return HiddenTrajectoryResult(violations=(Violation("S39", message),))
        return check_hidden_trajectory(envelope, stored, blobs)
    return gate.check_payload(envelope, stored, blobs, parent_contents)
