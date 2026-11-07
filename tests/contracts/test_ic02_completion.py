"""IC-02 0.7.1 is recorded as complete: the contract files COMPLETION.md pins still match."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "docs/architecture/contracts"
RECORD = CONTRACTS / "IC-02/0.7.1/COMPLETION.md"
TEXT = RECORD.read_text(encoding="utf-8")
ROWS = re.findall(r"^\| .*\| `([A-Za-z0-9/_.\-]+\.(?:json|md))` \| `([0-9a-f]{64})` \|$", TEXT, re.M)

PINNED = {
    "msr/geometry-measurement.schema.json",
    "msr/calibration.schema.json",
    "common/blob.schema.json",
    "msr/README.md",
    "msr/vectors/series.json",
    "msr/vectors/calibration-parents.json",
    "common/vectors/blob/blob-refs.json",
    "msr/archive/0.7.0/geometry-measurement.schema.json",
}


def test_record_pins_exactly_the_ic02_contract_files() -> None:
    assert {p for p, _ in ROWS} == PINNED and len(ROWS) == len(PINNED)


# Files the 0.8.0 change superseded: the record's bytes now live under msr/archive/ (verbatim copies).
SUPERSEDED = {
    "msr/calibration.schema.json": "msr/archive/0.7.0/calibration.schema.json",
    "msr/README.md": "msr/archive/0.7.1/README.md",
    "msr/vectors/calibration-parents.json": "msr/archive/0.7.1/calibration-parents.json",
}


@pytest.mark.parametrize(("path", "digest"), ROWS, ids=[p for p, _ in ROWS])
def test_pinned_contract_file_is_unchanged(path: str, digest: str) -> None:
    assert hashlib.sha256((CONTRACTS / SUPERSEDED.get(path, path)).read_bytes()).hexdigest() == digest, path


def test_record_states_the_commits_decision_and_draft_status() -> None:
    for needle in ("5473c5c", "d6b4774", "D-97", "v0.7.3", "草案（0.x）", "1.0.0 ではない"):
        assert needle in TEXT


def test_vector_counts_in_the_record_match_the_files() -> None:
    import json

    counts = {}
    for name in ("msr/vectors/series.json", "msr/vectors/calibration-parents.json", "common/vectors/blob/blob-refs.json"):
        cases = json.loads((CONTRACTS / SUPERSEDED.get(name, name)).read_text(encoding="utf-8"))["cases"]
        accepts = sum(c["expect"]["result"] == "accept" for c in cases)
        counts[name] = (len(cases), accepts, len(cases) - accepts)
    assert counts == {
        "msr/vectors/series.json": (9, 4, 5),
        "msr/vectors/calibration-parents.json": (12, 2, 10),
        "common/vectors/blob/blob-refs.json": (32, 8, 24),
    }
    for line in ("系列 9（受理 4・拒否 5）", "親の参照整合 12（受理 2・拒否 10）", "Blob 32（受理 8・拒否 24）"):
        assert line in TEXT
