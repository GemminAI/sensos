"""IC-00 1.1.0 FREEZE record (draft; status: not frozen, before independent verification).

Parallel to ``test_freeze.py`` (1.0.0), which is untouched. Reused from it: the row format and
the sha256 check. Written separately for 1.1.0: the file, the scope, the status needles, the version
assertions, the comparison with the 1.0.0 schema, the 1.1.0 lock, and the proof that the 1.0.0
freeze is unchanged.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest
from contracts.schemas import load_schema

ROOT = Path(__file__).resolve().parents[2]
C = "docs/architecture/contracts"
FREEZE_100 = ROOT / f"{C}/IC-00/1.0.0/FREEZE.md"
FREEZE_110 = ROOT / f"{C}/IC-00/1.1.0/FREEZE.md"
LOCK_110 = Path(__file__).with_name("contract-v110.lock")
ROW = r"^\| `([^`]+)` \| `([0-9a-f]{64})` \|$"
ROWS_110 = re.findall(ROW, FREEZE_110.read_text(encoding="utf-8"), re.M)
ROWS_100 = re.findall(ROW, FREEZE_100.read_text(encoding="utf-8"), re.M)

EXPECTED_110 = {
    f"{C}/IC-00/1.1.0/artifact.schema.json",
    "tools/contracts/ic00_v110.py",
    "tools/contracts/ic00_versions.py",
    f"{C}/IC-00/1.1.0/vectors/check-envelope.json",
    f"{C}/IC-00/1.1.0/vectors/parent-versions.json",
}


def _sha(path: str) -> str:
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


def test_1_1_0_freeze_lists_exactly_the_1_1_0_scope() -> None:
    paths = [p for p, _ in ROWS_110]
    assert len(paths) == len(set(paths))
    assert set(paths) == EXPECTED_110
    for out_of_scope in ("check-envelope-unspecified", "parent-versions-unspecified", "make_vectors", "schemas.py", "contract.lock", "common/", "IC-00/1.0.0"):
        assert not any(out_of_scope in p for p in paths), out_of_scope


@pytest.mark.parametrize(("path", "digest"), ROWS_110, ids=[p for p, _ in ROWS_110])
def test_1_1_0_recorded_file_is_unchanged(path: str, digest: str) -> None:
    assert _sha(path) == digest, f"{path} differs from the sha256 recorded in the 1.1.0 FREEZE.md"


def test_1_1_0_freeze_states_what_it_is_not() -> None:
    text = FREEZE_110.read_text(encoding="utf-8")
    assert "状態：未凍結" in text
    for needle in ("D-107", "D-108", "D-109", "D-110", "D-111", "D-112", "D-113", "D-114", "D-115", "D-116", "未規定", "parent-versions-unspecified.json", "未実装", "S28", "sensos-connector", "IC-06"):
        assert needle in text, needle
    assert "状態：検証済み" not in text and "状態：凍結" not in text


def test_1_1_0_schema_carries_the_1_1_0_version() -> None:
    schema = load_schema("IC-00/1.1.0/artifact.schema.json")
    assert schema["$id"] == "sensos:contracts/IC-00/artifact/1.1.0"
    assert schema["properties"]["contract"]["properties"]["version"] == {"const": "1.1.0"}
    assert schema["allOf"] == [{"$ref": "sensos:contracts/common/provenance/1.0.0"}]


def test_1_1_0_schema_differs_from_1_0_0_only_in_id_version_and_description() -> None:
    old = (ROOT / f"{C}/common/artifact.schema.json").read_text(encoding="utf-8")
    new = (ROOT / f"{C}/IC-00/1.1.0/artifact.schema.json").read_text(encoding="utf-8")

    def strip(text: str) -> list[str]:
        return [ln for ln in text.splitlines() if '"description"' not in ln and '"$id"' not in ln]

    old_lines = strip(old.replace('{ "const": "1.0.0" }', '{ "const": "1.1.0" }'))
    assert old_lines == strip(new)


def test_1_1_0_lock_matches_files() -> None:
    lock = json.loads(LOCK_110.read_text(encoding="utf-8"))
    assert lock["contract_id"] == "IC-00" and lock["version"] == "1.1.0"
    assert lock["status"] == "draft (not frozen)"
    for entry in lock["schemas"] + lock["reuses_frozen_1_0_0"]:
        assert _sha(f"{C}/{entry['path']}") == entry["sha256"], entry["path"]
        assert load_schema(entry["path"])["$id"] == entry["id"]
    assert [e["id"] for e in lock["schemas"]] == ["sensos:contracts/IC-00/artifact/1.1.0"]
    assert [e["id"] for e in lock["reuses_frozen_1_0_0"]] == ["sensos:contracts/common/provenance/1.0.0"]


def test_1_0_0_freeze_is_untouched_by_1_1_0() -> None:
    """The 15 files of the 1.0.0 freeze still have the recorded sha256 and the 1.0.0 FREEZE.md still
    lists exactly them (the 1.0.0 freeze test itself is test_freeze.py)."""
    assert len(ROWS_100) == 15
    for path, digest in ROWS_100:
        assert _sha(path) == digest, path
    assert not any("1.1.0" in p or "v110" in p or "ic00_versions" in p for p, _ in ROWS_100)
