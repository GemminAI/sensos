"""Entry for the payloads of the nvs contracts, beside ``gate.py`` (which is pinned by the IC-02 0.10.0 lock).

``check_nvs_payload`` has two kinds of return value:

* ``nvs.hidden-trajectory`` ``0.1.0``: ``check_hidden_trajectory`` and nothing else (``gate.check_payload`` is
  not called); the result is a ``HiddenTrajectoryResult`` (violations and UNVERIFIABLE).
* ``nvs.token-temporal`` ``0.1.0``: ``check_token_temporal`` and its ``list[Violation]`` as it is.
  Another version is ``S39``. ``gate.PAYLOAD_SCHEMAS`` is not extended.
* ``nvs.meaning-measurement`` ``0.1.0``: ``check_meaning_measurement`` and its ``HiddenTrajectoryResult``.
  Another version is ``S39``, in a ``HiddenTrajectoryResult``. ``gate.PAYLOAD_SCHEMAS`` is not extended.
* ``nvs.meaning-frame`` ``0.1.0``: ``check_meaning_frame`` and its ``HiddenTrajectoryResult``.
  Another version is ``S39``, in a ``HiddenTrajectoryResult``. ``gate.PAYLOAD_SCHEMAS`` is not extended.
* any other ``payload_schema``: ``gate.check_payload`` with the same arguments and its return value as it is
  (``list[Violation]``; an unknown id is ``S39``, as before).

``contract_facts`` (keyword only) is passed to ``check_hidden_trajectory`` for ``nvs.hidden-trajectory`` 0.1.0 and
is not used for anything else, so the delegation to ``gate.check_payload`` is as it was.

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
from contracts.meaning_frame import PAYLOAD_SCHEMA_ID as FRAME_SCHEMA_ID
from contracts.meaning_frame import PAYLOAD_SCHEMA_VERSION as FRAME_SCHEMA_VERSION
from contracts.meaning_frame import check_meaning_frame
from contracts.meaning_measurement import check_meaning_measurement
from contracts.token_temporal import check_token_temporal


def check_nvs_payload(
    envelope: Mapping[str, Any],
    stored: Mapping[str, Any] | None = None,
    blobs: Mapping[str, bytes] | None = None,
    parent_contents: Mapping[str, str] | None = None,
    *,
    contract_facts: Mapping[str, Any] | None = None,
) -> HiddenTrajectoryResult | list[Violation]:
    declared = envelope["payload_schema"]
    if declared["id"] == PAYLOAD_SCHEMA_ID:
        if declared["version"] != PAYLOAD_SCHEMA_VERSION:
            message = f"unknown payload_schema {declared['id']} {declared['version']}"
            return HiddenTrajectoryResult(violations=(Violation("S39", message),))
        return check_hidden_trajectory(
            envelope, stored, blobs, contract_facts=contract_facts
        )
    if declared["id"] == "nvs.token-temporal":
        if declared["version"] != "0.1.0":
            message = f"unknown payload_schema {declared['id']} {declared['version']}"
            return [Violation("S39", message)]
        return check_token_temporal(envelope, stored, blobs)
    if declared["id"] == FRAME_SCHEMA_ID:
        if declared["version"] != FRAME_SCHEMA_VERSION:
            message = f"unknown payload_schema {declared['id']} {declared['version']}"
            return HiddenTrajectoryResult(violations=(Violation("S39", message),))
        return check_meaning_frame(envelope, stored, blobs)
    if declared["id"] == "nvs.meaning-measurement":
        if declared["version"] != "0.1.0":
            message = f"unknown payload_schema {declared['id']} {declared['version']}"
            return HiddenTrajectoryResult(violations=(Violation("S39", message),))
        return check_meaning_measurement(envelope, stored, blobs)
    return gate.check_payload(envelope, stored, blobs, parent_contents)
