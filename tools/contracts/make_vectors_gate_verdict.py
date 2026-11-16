"""Generate the GateVerdict (gate-verdict/1) examples
(docs/architecture/contracts/nvs/vectors/gate-verdict.json).

Run:  python tools/contracts/make_vectors_gate_verdict.py  (from the repository root)

New in U6T-1a. It imports the schema loader, the validator of the schema and ``contracts.jcs``; nothing
of the Gate. Output is deterministic (indent=1, sorted keys, ensure_ascii=False, trailing newline, like
make_vectors_hidden_trajectory.py).

The values are ILLUSTRATIVE: the ids are made from fixed text, the checker files and their hashes are not
the real ones. The examples show the form; ``verdict_sha256`` is real (the JCS of the document without it),
and the generator refuses to write a file whose example the schema does not accept or whose hash is wrong.
"""

from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jsonschema import Draft202012Validator

from contracts.jcs import jcs
from contracts.schemas import load_schema

SCHEMA = "nvs/gate-verdict.schema.json"
OUT = (
    Path(__file__).resolve().parents[2]
    / "docs/architecture/contracts/nvs/vectors/gate-verdict.json"
)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _id(prefix: str, text: str) -> str:
    return f"{prefix}:{_sha(text)}"


ARTIFACT = _id("art", "example-artifact")
CONTENT = _id("cnt", "example-content")
PARENT = _id("art", "example-parent")
PARENT_CONTENT = _id("cnt", "example-parent-content")
OBSERVATION = _id("obs", "example-observation")

FILES = [
    {"repo": "nvs-runtime", "path": "src/nvs_runtime/hidden_trajectory/_gate_child.py"},
    {"repo": "nvs-runtime", "path": "src/nvs_runtime/hidden_trajectory/gate_client.py"},
    {"repo": "sensos", "path": "tools/contracts/gate_nvs.py"},
    {"repo": "sensos", "path": "tools/contracts/hidden_trajectory.py"},
]


def _base(*, with_parent: bool) -> dict[str, Any]:
    """A PASS verdict about a hidden-trajectory envelope; the examples change it."""
    lookup = (
        {
            PARENT: {
                "content_id": PARENT_CONTENT,
                "seq": 1,
                "observation_id": OBSERVATION,
            }
        }
        if with_parent
        else {}
    )
    return {
        "verdict_version": "gate-verdict/1",
        "subject": {
            "artifact_id": ARTIFACT,
            "content_id": CONTENT,
            "envelope_sha256": _sha("example-envelope"),
        },
        "result": "PASS",
        "layers": {
            "L1": {"status": "PASS", "codes": []},
            "L2": {"status": "PASS", "kind": "hidden_trajectory", "codes": []},
            "L3": {"status": "not_applicable", "codes": []},
        },
        "codes": [],
        "violations": [],
        "unverifiable": [],
        "waived": [],
        "rules": {
            "ic00_contract_version": "1.1.0",
            "payload_schema": {"id": "nvs.hidden-trajectory", "version": "0.1.0"},
        },
        "inputs": {
            "lookup": lookup,
            "lookup_sha256": _sha(json.dumps(lookup, sort_keys=True)),
            "stored": [],
            "blobs_checked": sorted(
                [_sha("example-points"), _sha("example-token-index")]
            ),
            "contract_facts_sha256": _sha("example-contract-facts"),
        },
        "gate": {
            "checker": {
                "bundle_sha256": _sha("example-bundle"),
                "sensos_commit": "4cdb968" + "0" * 33,
                "nvs_runtime_commit": None,
                "files": [dict(f, sha256=_sha(f["path"])) for f in FILES],
            },
            "runtime": {
                "python": "3.14.7",
                "implementation": "CPython",
                "packages": {"jsonschema": "4.26.0", "referencing": "0.37.0"},
                "platform": {"system": "Darwin", "machine": "arm64"},
            },
            "unverifiable_catalog": {
                "version": "4cdb968" + "0" * 33,
                "sha256": _sha("catalog"),
            },
        },
        "produced_by": {"name": "nvs-runtime", "version": "1.0.0", "build": "example"},
        "verdict_sha256": "0" * 64,
    }


def seal(verdict: dict[str, Any]) -> dict[str, Any]:
    """``verdict_sha256`` = SHA-256 of the JCS of everything else."""
    body = {k: v for k, v in verdict.items() if k != "verdict_sha256"}
    verdict["verdict_sha256"] = hashlib.sha256(jcs(body)).hexdigest()
    return verdict


def examples() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []

    out.append(
        {
            "id": "pass",
            "description": "L1 and L2 pass; blobs and contract facts were given; no window",
            "verdict": seal(_base(with_parent=True)),
        }
    )

    unverified = _base(with_parent=False)
    unverified["result"] = "PASS_UNVERIFIED"
    unverified["layers"]["L2"]["status"] = "PASS_UNVERIFIED"
    unverified["unverifiable"] = [
        {"layer": "L2", "check": "contract_binding", "reason": "contract_not_supplied"},
        {"layer": "L2", "check": "points_bytes", "reason": "blob_not_supplied"},
    ]
    unverified["inputs"]["blobs_checked"] = []
    unverified["inputs"]["contract_facts_sha256"] = None
    out.append(
        {
            "id": "pass-unverified",
            "description": "nothing is violated; the Blobs and the contract facts were not given, so two checks cannot be made",
            "verdict": seal(unverified),
        }
    )

    l1 = _base(with_parent=True)
    l1["result"] = "FAIL"
    l1["layers"] = {
        "L1": {"status": "FAIL", "codes": ["S8"]},
        "L2": {"status": "not_run", "kind": None, "codes": []},
        "L3": {"status": "not_run", "codes": []},
    }
    l1["codes"] = ["S8"]
    l1["violations"] = [
        {"layer": "L1", "code": "S8", "message": "parent is not in the lookup"}
    ]
    l1["inputs"]["lookup"] = {}
    l1["inputs"]["lookup_sha256"] = _sha(json.dumps({}, sort_keys=True))
    out.append(
        {
            "id": "fail-l1",
            "description": "the envelope rule fails (S8); the payload and the window are not run",
            "verdict": seal(l1),
        }
    )

    l2 = _base(with_parent=False)
    l2["result"] = "FAIL"
    l2["layers"]["L2"] = {
        "status": "FAIL",
        "kind": "hidden_trajectory",
        "codes": ["E_TRAJ_SYNTHETIC"],
    }
    l2["codes"] = ["E_TRAJ_SYNTHETIC"]
    l2["violations"] = [
        {
            "layer": "L2",
            "code": "E_TRAJ_SYNTHETIC",
            "message": "the contract is synthetic",
        }
    ]
    out.append(
        {
            "id": "fail-l2",
            "description": "the envelope is well formed; the payload check fails (E_TRAJ_SYNTHETIC)",
            "verdict": seal(l2),
        }
    )

    window = _base(with_parent=True)
    window["result"] = "PASS_UNVERIFIED"
    window["layers"]["L2"] = {"status": "PASS", "kind": "ic02", "codes": []}
    window["layers"]["L3"] = {"status": "PASS_UNVERIFIED", "codes": []}
    window["rules"]["payload_schema"] = {
        "id": "msr.trajectory-window",
        "version": "0.10.0",
    }
    window["unverifiable"] = [
        {
            "layer": "L3",
            "check": "window_space_derivation",
            "reason": "rule_not_derivable",
        }
    ]
    window["inputs"]["stored"] = [PARENT]
    window["inputs"]["contract_facts_sha256"] = None
    out.append(
        {
            "id": "pass-unverified-window",
            "description": "a msr.trajectory-window payload: L2 is IC-02, L3 (the window space) is checked and one derivation cannot be",
            "verdict": seal(window),
        }
    )
    return out


def main() -> None:
    schema = load_schema(SCHEMA)
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    cases = examples()
    for case in cases:
        errors = sorted(
            validator.iter_errors(case["verdict"]), key=lambda e: list(e.absolute_path)
        )
        if errors:
            raise SystemExit(
                f"{case['id']}: the schema refuses it: {errors[0].message}"
            )
        again = seal(copy.deepcopy(case["verdict"]))
        if again["verdict_sha256"] != case["verdict"]["verdict_sha256"]:
            raise SystemExit(f"{case['id']}: verdict_sha256 is not stable")
    doc = {
        "format": "gate-verdict-examples/1",
        "schema": SCHEMA,
        "rule": "Each verdict is accepted by the schema (draft 2020-12), and its verdict_sha256 is the SHA-256 of the JCS (contracts/jcs.py) of the verdict without that key. The values (ids, hashes of files, versions) are illustrative.",
        "status": "草案 (gate-verdict/1。U6T-1a。適格性・鎖への採用・時刻は入れない：D-185 (9)、DC-T1-2)",
        "cases": cases,
    }
    OUT.write_text(
        json.dumps(doc, indent=1, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"{len(cases)} examples -> {OUT}")


if __name__ == "__main__":
    main()
