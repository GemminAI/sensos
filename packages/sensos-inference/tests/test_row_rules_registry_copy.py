"""DC-T2b-3: ``ROW_RULES`` (U1) against the row-rule registry of the contract side (U5).

The registry of ``nvs.hidden-trajectory`` row rules is ``hid_row_rules.json`` on the contract side
(sensos ``feature/u5-hidden-trajectory``, ``tools/contracts/hid_row_rules.json``); it is the source of
truth. This package keeps a byte-for-byte copy of it (``contract_copies/``) with a lock, and these
tests hold ``observation.ROW_RULES`` to that copy. A name or a definition that drifts on either side
fails here instead of failing every capture at HT-07.

Always run: the copy against its lock, and ``ROW_RULES`` against the copy. Opt-in: set
``HID_ROW_RULES_SOURCE_ROOT`` to a sensos checkout that has ``tools/contracts/hid_row_rules.json``
and the copy is compared with it byte for byte.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

import pytest

from sensos_inference.observation import ROW_RULES

HERE = Path(__file__).resolve().parent / "contract_copies"
COPY = HERE / "hid_row_rules.json"
LOCK = HERE / "hid_row_rules.copy.lock.json"
SOURCE_ENV = "HID_ROW_RULES_SOURCE_ROOT"
ORDER = (
    "When a row rule is added or changed: register it first on the contract side "
    "(tools/contracts/hid_row_rules.json, sensos feature/u5-hidden-trajectory), then take the copy "
    "again (byte for byte), update hid_row_rules.copy.lock.json, and then change ROW_RULES (DC-T2b-3)."
)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _registry() -> dict[str, Any]:
    registry: dict[str, Any] = json.loads(COPY.read_bytes())
    return registry


def test_the_copy_is_the_one_the_lock_names() -> None:
    lock = json.loads(LOCK.read_bytes())
    digest = _sha(COPY.read_bytes())
    assert lock["copy"]["sha256"] == digest, (
        f"the copy changed without the lock. {ORDER}"
    )
    assert lock["source"]["sha256"] == digest, (
        f"the copy is not the source's bytes. {ORDER}"
    )
    assert re.fullmatch(r"[0-9a-f]{64}", lock["source"]["sha256"])
    assert lock["source"]["path"] == "tools/contracts/hid_row_rules.json"
    assert lock["source"]["branch"] and lock["source"]["commit"]
    assert _registry()["format"] == "hid-row-rules/1"


def test_row_rules_has_exactly_the_registered_names() -> None:
    registered = set(_registry()["rules"])
    assert set(ROW_RULES) == registered, (
        f"ROW_RULES only: {sorted(set(ROW_RULES) - registered)}; "
        f"registry only: {sorted(registered - set(ROW_RULES))}. {ORDER}"
    )


def test_every_rule_has_the_registered_kind_and_alignment() -> None:
    registry = _registry()
    differences = {
        name: {
            "ROW_RULES": {"kind": spec.kind, "alignment": spec.alignment},
            "registry": registry["rules"][name],
        }
        for name, spec in ROW_RULES.items()
        if name in registry["rules"]
        and registry["rules"][name] != {"kind": spec.kind, "alignment": spec.alignment}
    }
    assert not differences, f"{differences}. {ORDER}"


def test_every_name_fits_the_registry_pattern_and_its_kind_slug() -> None:
    registry = _registry()
    pattern = re.compile(registry["base_rule_pattern"])
    slugs: dict[str, str] = registry["kind_slugs"]
    for name, spec in ROW_RULES.items():
        assert pattern.fullmatch(name), (
            f"{name} does not fit base_rule_pattern. {ORDER}"
        )
        slug = next(
            (s for s in slugs if name.rsplit("/", 1)[0].endswith(f"-{s}")), None
        )
        assert slug is not None and slugs[slug] == spec.kind, (
            f"{name}: the kind slug in the name is not its kind {spec.kind}. {ORDER}"
        )


@pytest.mark.skipif(
    not os.environ.get(SOURCE_ENV)
    or not (
        Path(os.environ.get(SOURCE_ENV, "")) / "tools/contracts/hid_row_rules.json"
    ).is_file(),
    reason=f"{SOURCE_ENV} is not set to a sensos checkout with tools/contracts/hid_row_rules.json",
)
def test_the_copy_is_the_source_of_truth_byte_for_byte() -> None:
    source = Path(os.environ[SOURCE_ENV]) / "tools/contracts/hid_row_rules.json"
    assert source.read_bytes() == COPY.read_bytes(), (
        f"the source changed or the copy did. {ORDER}"
    )
