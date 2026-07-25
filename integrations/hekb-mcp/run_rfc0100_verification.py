"""Runs the RFC-NVS-0100 verification suite against the REAL encoder
(SentenceTransformerEncoder, paraphrase-multilingual-MiniLM-L12-v2) and
writes the full JSON report to hekb_mcp/data/rfc0100_verification_report.json.

Run with:  PYTHONPATH=. hekb_mcp/.venv/bin/python -m hekb_mcp.run_rfc0100_verification
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from hekb_mcp.observation_engine import SentenceTransformerEncoder
from hekb_mcp.rfc0100_verification import run_full_verification

OUTPUT_PATH = Path(__file__).parent / "data" / "rfc0100_verification_report.json"


def main() -> None:
    encoder = SentenceTransformerEncoder()
    print(f"Loading {encoder.MODEL_NAME} ...")
    start = time.time()
    report = run_full_verification(encoder, encoder_name=encoder.MODEL_NAME, n_injection_trials=500)
    elapsed = time.time() - start
    print(f"Verification run completed in {elapsed:.1f}s")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    print(f"Wrote {OUTPUT_PATH}")

    print("\n=== Summary ===")
    print(f"Hypothesis 0 (Projection Existence): {'PASS' if report.hypothesis0.passed else 'FAIL'}")
    print(f"Hypothesis 1 (Chart-Local Uniqueness / SD<=0.025): max_group_sd={report.hypothesis1.max_group_sd:.4f} -> {'PASS' if report.hypothesis1.passed else 'FAIL'}")
    print(f"Hypothesis 2 (Lipschitz Stability / LDR<=1.85): ldr={report.hypothesis2.ldr:.4f} -> {'PASS' if report.hypothesis2.passed else 'FAIL'}")
    print(f"Hypothesis 3 (Chart/Attractor Resolution): CRA={report.hypothesis3.cra:.4f} (>=0.98) ARA={report.hypothesis3.ara:.4f} (>=0.95) -> {'PASS' if report.hypothesis3.passed else 'FAIL'}")
    print(f"Hypothesis 4 (Adversarial Residual Spike): block_rate={report.hypothesis4.injection_block_rate:.4f} (need 1.0) -> {'PASS' if report.hypothesis4.passed else 'FAIL'}")
    print(f"CTS-ENH-004: {'PASS' if report.cts_enh_004_pass else 'FAIL'}")
    print(f"CTS-ENT-004: {'PASS' if report.cts_ent_004_pass else 'FAIL'}")


if __name__ == "__main__":
    main()
