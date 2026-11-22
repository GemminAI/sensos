"""U5 import boundary, read statically with ``ast`` (nothing is imported to find out).

``test_units.py`` already holds the rule for every ``tools/contracts/*.py`` (stdlib, jsonschema, referencing,
contracts). Here the U5 modules are named, so that none of them can be left out by accident, and the U5 tests are
checked too: neither side imports a package of another repository (``nvs``, ``nvs_edge``, ``nvs_runtime``,
``sensos_inference`` ...). The C14 sample is a static JSON file that is only read."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools" / "contracts"
TESTS = ROOT / "tests" / "contracts"

U5_MODULES = [
    "hid_space.py",
    "hidden_trajectory_registry.py",
    "hidden_trajectory.py",
    "hidden_trajectory_window.py",
    "gate_nvs.py",
    "contract_facts.py",
    "make_vectors_hidden_trajectory.py",
]
U5_TESTS = [
    "test_float32_blob.py",
    "test_hid_space.py",
    "test_hidden_trajectory.py",
    "test_hidden_trajectory_schema.py",
    "test_hidden_trajectory_contract.py",
    "test_hidden_trajectory_status.py",
    "test_contract_facts.py",
    "test_window_space.py",
    "test_gate_nvs.py",
    "test_hid_row_rules.py",
]
#: packages of the other repositories (and the product itself): never imported from here
FOREIGN = {
    "nvs",
    "nvs_edge",
    "nvs_runtime",
    "nvs_kernel",
    "sensos_inference",
    "sensos",
    "sensos_core",
    "gemmin",
}
STDLIB = set(sys.stdlib_module_names) | {"__future__"}
TOOLS_OK = STDLIB | {"jsonschema", "referencing", "contracts"}
#: ``make_vectors`` is found through ``sys.path`` (conftest), as in the existing tests; ``pytest`` is the runner
SIBLING_TESTS = {p.stem for p in TESTS.glob("*.py")}
TESTS_OK = TOOLS_OK | {"pytest", "make_vectors"} | SIBLING_TESTS


def _imports(path: Path) -> list[tuple[str, int]]:
    """(top-level package, relative level) of every import, and of every ``__import__`` / ``import_module`` call."""
    found: list[tuple[str, int]] = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found += [(a.name.split(".")[0], 0) for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            found.append(((node.module or "").split(".")[0], node.level))
        elif isinstance(node, ast.Call):
            name = (
                node.func.id
                if isinstance(node.func, ast.Name)
                else node.func.attr
                if isinstance(node.func, ast.Attribute)
                else ""
            )
            if name in {"__import__", "import_module"} and node.args:
                arg = node.args[0]
                found.append(
                    (
                        str(arg.value).split(".")[0]
                        if isinstance(arg, ast.Constant)
                        else "<dynamic>",
                        0,
                    )
                )
    return found


def test_the_u5_files_exist() -> None:
    assert all((TOOLS / n).is_file() for n in U5_MODULES)
    assert all((TESTS / n).is_file() for n in U5_TESTS)


@pytest.mark.parametrize("name", U5_MODULES)
def test_u5_modules_import_only_stdlib_jsonschema_referencing_and_contracts(
    name: str,
) -> None:
    for top, level in _imports(TOOLS / name):
        assert level == 0, (name, "relative import")
        assert top not in FOREIGN, (name, top)
        allowed = TOOLS_OK | (
            {"make_vectors"} if name == "make_vectors_hidden_trajectory.py" else set()
        )
        assert top in allowed, (name, top)


@pytest.mark.parametrize("name", U5_TESTS)
def test_u5_tests_do_not_import_another_repository(name: str) -> None:
    for top, level in _imports(TESTS / name):
        assert level == 0, (name, "relative import")
        assert top not in FOREIGN, (name, top)
        assert top in TESTS_OK, (name, top)


def test_the_scan_does_find_imports() -> None:
    seen = {top for n in U5_MODULES for top, _ in _imports(TOOLS / n)}
    assert {"contracts", "json", "hashlib"} <= seen
    assert {"pytest", "contracts"} <= {
        top for top, _ in _imports(TESTS / "test_window_space.py")
    }


def test_the_scan_catches_a_foreign_import(tmp_path: Path) -> None:
    bad = tmp_path / "bad.py"
    bad.write_text(
        "import nvs_edge.x\nfrom nvs_runtime import y\n__import__('sensos_inference')\n",
        encoding="utf-8",
    )
    assert {top for top, _ in _imports(bad)} == {
        "nvs_edge",
        "nvs_runtime",
        "sensos_inference",
    }
    assert {top for top, _ in _imports(bad)} <= FOREIGN
