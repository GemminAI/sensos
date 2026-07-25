"""Fast plumbing smoke test for the verification suite (FakeTrigramEncoder,
not the real semantic model — see fake_encoder.py). Confirms every hypothesis
check runs end-to-end and produces well-typed, JSON-serializable output. Does
NOT validate real semantic quality — see run_rfc0100_verification.py and
EXPERIMENT_REPORT_RFC0100.md for the real-encoder run and its actual numbers.
"""

from __future__ import annotations

import json

from hekb_mcp.rfc0100_verification import run_full_verification
from hekb_mcp.tests.fake_encoder import FakeTrigramEncoder


def test_verification_suite_runs_end_to_end_and_is_json_serializable():
    report = run_full_verification(FakeTrigramEncoder(), "FakeTrigramEncoder(test)", n_injection_trials=10)

    assert report.hypothesis0.total_samples > 0
    assert report.hypothesis3.n_queries == 24
    assert report.hypothesis4.n_injection_trials == 10
    # Must not raise, and must not silently stringify booleans (regression
    # guard for numpy.bool_ leaking into dataclass fields).
    serialized = json.dumps(report.to_dict())
    parsed = json.loads(serialized)
    assert parsed["hypothesis3"]["cra_significant"] in (True, False)
    assert parsed["hypothesis3"]["ara_significant"] in (True, False)
