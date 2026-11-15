"""The row-rule registry of nvs.hidden-trajectory (tools/contracts/hid_row_rules.json, design U5 v0.2 6.2).

The registry is pinned here by its content and structure. The comparison with sensos-inference
``observation.ROW_RULES`` (U1) is NOT made here: that package is not on this branch, and the checker never
imports it. It is a task for the U1 side (a test there that imports both and compares them), see
``test_the_u1_comparison_is_left_to_the_u1_side``.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import pytest
from contracts import hidden_trajectory as ht

ROOT = Path(__file__).resolve().parents[2]
REGISTRY_FILE = ROOT / "tools/contracts/hid_row_rules.json"
REGISTRY: dict[str, Any] = json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))
LOCK = json.loads(
    Path(__file__).with_name("contract-hid-row-rules.lock").read_text(encoding="utf-8")
)

EXPECTED_RULES = {
    "qwen35-mlx-mlp-out/1": ("mlp_out", "decides-next/1"),
    "qwen35-mlx-block-out/1": ("block_out", "decides-next/1"),
    "qwen35-mlx-final-norm/1": ("final_norm", "decides-next/1"),
    "llama31-mlx-final-norm/1": ("final_norm", "decides-next/1"),
}
BASE_PATTERN = (
    r"^[a-z0-9]+(?:-[a-z0-9]+)*-(?:block-out|mlp-out|final-norm)/[1-9][0-9]*$"
)


def test_lock_matches_the_file() -> None:
    (entry,) = LOCK["files"]
    assert entry["path"] == "tools/contracts/hid_row_rules.json"
    assert hashlib.sha256(REGISTRY_FILE.read_bytes()).hexdigest() == entry["sha256"]
    assert LOCK["contract_id"] == "nvs/hid-row-rules"


def test_the_four_rows_of_the_design() -> None:
    assert {
        k: (v["kind"], v["alignment"]) for k, v in REGISTRY["rules"].items()
    } == EXPECTED_RULES
    assert all(set(v) == {"kind", "alignment"} for v in REGISTRY["rules"].values())
    assert REGISTRY["format"] == "hid-row-rules/1"


def test_the_base_form_pattern_is_fixed_and_equals_the_schema_and_hid_space() -> None:
    assert REGISTRY["base_rule_pattern"] == BASE_PATTERN
    schema = json.loads(
        (
            ROOT / "docs/architecture/contracts/nvs/hidden-trajectory.schema.json"
        ).read_text(encoding="utf-8")
    )
    assert schema["properties"]["row_rule"]["pattern"] == BASE_PATTERN


def test_kind_slugs_map_to_kinds() -> None:
    assert REGISTRY["kind_slugs"] == {
        "block-out": "block_out",
        "mlp-out": "mlp_out",
        "final-norm": "final_norm",
    }


@pytest.mark.parametrize("row_rule", list(EXPECTED_RULES))
def test_every_registered_rule_is_a_base_rule_whose_slug_gives_its_kind(
    row_rule: str,
) -> None:
    assert re.fullmatch(BASE_PATTERN, row_rule)
    slug = re.search(r"-(block-out|mlp-out|final-norm)/", row_rule)
    assert slug is not None
    assert REGISTRY["kind_slugs"][slug.group(1)] == REGISTRY["rules"][row_rule]["kind"]


def test_the_checker_reads_this_file() -> None:
    assert ht.REGISTRY_PATH == REGISTRY_FILE
    assert {k: dict(v) for k, v in ht.row_rule_registry().items()} == REGISTRY["rules"]


@pytest.mark.parametrize(
    "not_a_base_rule",
    [
        "qwen35-mlx-mlp-out/1+rows0+128/1",
        "qwen35-mlx/1",
        "Qwen35-mlx-mlp-out/1",
        "qwen35-mlx-mlp-out/0",
        "all rows of the mlp out",
        "",
    ],
)
def test_other_forms_are_not_base_rules(not_a_base_rule: str) -> None:
    assert re.fullmatch(BASE_PATTERN, not_a_base_rule) is None


def test_the_u1_comparison_is_left_to_the_u1_side() -> None:
    """sensos-inference ``observation.ROW_RULES`` is not on this branch (and is never imported by the checker).

    Homework for the U1 side: a test that imports both ``observation.ROW_RULES`` and this JSON and asserts that
    the sets of row rules, their kinds and their alignments are equal. Until then the JSON is the contract's copy."""
    source = (ROOT / "tools/contracts/hidden_trajectory.py").read_text(encoding="utf-8")
    assert (
        "import sensos_inference" not in source
        and "from sensos_inference" not in source
    )
    assert "observation" not in {
        line.split()[1] for line in source.splitlines() if line.startswith("import ")
    }
