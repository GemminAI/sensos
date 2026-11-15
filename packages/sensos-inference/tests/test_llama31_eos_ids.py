"""``eos_ids`` in the Llama capture result (U2): the stop ids the capture loop used.

(i) is a plain test. (ii) and (iii) are strict xfail: ``observation.from_llama31`` does not read
``eos_ids`` today (``_build_provenance(..., qwen=False)``) and has no end-of-sequence check, so the
Llama path stays "unknown" and does not reject an EOS id among the generated tokens. They are
recorded as the known gap; once U1's converter handles Llama they flip and must be un-marked.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
from test_llama31_capture import EOS, _provider

from sensos_inference.observation import ObservationError, from_llama31

MESSAGES = [{"role": "user", "content": "x"}]
CONVERT = {"model_build_id": "fake-llama", "compute_environment": "fake"}


def test_result_reports_the_stop_ids_the_loop_used(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    result = provider.capture_chat(MESSAGES, max_tokens=64, seed=3)
    assert result.eos_ids == [EOS]
    assert result.eos_ids == sorted(provider._eos_ids())  # what the loop was given
    assert result.summary()["eos_ids"] == [EOS]


def test_a_failed_capture_does_not_claim_an_empty_set(tmp_path: Path) -> None:
    def broken(_target: str) -> tuple[object, object]:
        raise RuntimeError("no model")

    provider = _provider(tmp_path)
    provider._loader = broken
    result = provider.capture_chat(MESSAGES, max_tokens=4, seed=1)
    assert not result.ok and result.eos_ids is None


@pytest.mark.xfail(strict=True, reason="from_llama31 does not read eos_ids yet (U1 converter)")
def test_conversion_carries_eos_ids_into_the_provenance(tmp_path: Path) -> None:
    result = _provider(tmp_path).capture_chat(MESSAGES, max_tokens=64, seed=3)
    capture = from_llama31(result, **CONVERT)
    assert capture.provenance.eos_ids == (EOS,)
    assert "provenance.eos_ids" not in capture.unknowns


@pytest.mark.xfail(strict=True, reason="from_llama31 has no EOS-in-generated-tokens check yet")
def test_conversion_rejects_an_eos_id_among_the_generated_tokens(tmp_path: Path) -> None:
    result = _provider(tmp_path).capture_chat(MESSAGES, max_tokens=64, seed=3)
    bad_ids = list(result.token_ids) + [EOS]
    states = np.vstack([result.states, result.states[-1:]])
    bad = replace(result, token_ids=bad_ids, states=states)
    with pytest.raises(ObservationError):
        from_llama31(bad, **CONVERT)
