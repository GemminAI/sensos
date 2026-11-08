"""IC-00 1.0.0 is frozen: every file FREEZE.md lists must still have the recorded sha256."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path

import pytest
from contracts.schemas import load_schema

ROOT = Path(__file__).resolve().parents[2]
FREEZE = ROOT / "docs/architecture/contracts/IC-00/1.0.0/FREEZE.md"
ROWS = re.findall(r"^\| `([^`]+)` \| `([0-9a-f]{64})` \|$", FREEZE.read_text(encoding="utf-8"), re.M)

EXPECTED = {
    *(f"docs/architecture/contracts/common/{n}.schema.json" for n in ("artifact", "provenance", "uncertainty")),
    *(f"tools/contracts/{n}.py" for n in ("__init__", "errors", "strict_load", "jcs", "quantize", "ids", "check")),
    *(
        f"docs/architecture/contracts/common/vectors/{n}.json"
        for n in ("canonicalize", "quantize", "ids", "envelope-ids", "check-envelope")
    ),
}


def test_freeze_lists_exactly_the_frozen_scope() -> None:
    paths = [p for p, _ in ROWS]
    assert len(paths) == len(set(paths))
    assert set(paths) == EXPECTED
    for out_of_scope in ("blob", "gate", "ic02", "msr/", "make_vectors", "schemas.py"):
        assert not any(out_of_scope in p for p in paths), out_of_scope


@pytest.mark.parametrize(("path", "digest"), ROWS, ids=[p for p, _ in ROWS])
def test_frozen_file_is_unchanged(path: str, digest: str) -> None:
    assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest, f"{path} changed after the 1.0.0 freeze"


def test_freeze_records_decisions_and_design_hash() -> None:
    text = FREEZE.read_text(encoding="utf-8")
    for needle in ("2026-11-06", "D-95", "D-96", "contracts/ic00-v1.0.0"):
        assert needle in text
    assert "f4a865ccf58027c64ed4b9197bc9bd0ebb76fa8f63bd69e1bf7c7a7dd137b911" in text


def test_frozen_schemas_carry_the_1_0_0_version() -> None:
    for name in ("artifact", "provenance", "uncertainty"):
        assert load_schema(f"common/{name}.schema.json")["$id"] == f"sensos:contracts/common/{name}/1.0.0"
    artifact = load_schema("common/artifact.schema.json")
    assert artifact["properties"]["contract"]["properties"]["version"] == {"const": "1.0.0"}


def test_schemas_differ_from_0_6_2_only_in_version_strings_and_description() -> None:
    def strip(text: str) -> str:
        return "\n".join(ln for ln in text.splitlines() if '"description"' not in ln)

    for name in ("artifact", "provenance", "uncertainty"):
        rel = f"docs/architecture/contracts/common/{name}.schema.json"
        shown = subprocess.run(["git", "-C", str(ROOT), "show", f"6a34b99:{rel}"], capture_output=True, check=False)
        if shown.returncode != 0:
            pytest.skip("6a34b99 not in the local checkout")
        old = shown.stdout.decode("utf-8").replace("0.6.2", "1.0.0")
        assert strip(old) == strip((ROOT / rel).read_text(encoding="utf-8")), name


def test_ids_do_not_depend_on_descriptions() -> None:
    from contracts import ids

    vec = json.loads((ROOT / "docs/architecture/contracts/common/vectors/envelope-ids.json").read_text("utf-8"))
    lookup = vec["lookup"]
    for case in vec["cases"]:
        assert ids.content_id(case["envelope"], lookup) == case["expect"]["content_id"]
        assert ids.artifact_id(case["envelope"], lookup) == case["expect"]["artifact_id"]
