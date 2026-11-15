"""``eos_ids`` in the Llama capture result (U2) and in the U1 converter ``from_llama31``.

The converter reads ``eos_ids`` into the provenance and refuses an EOS id among the generated
tokens (``OBS_SRC_EOS``), with the same meaning as ``from_qwen35``. ``None`` (not reported) is not
checked and stays unknown; an empty list is "known to be empty" (nothing to refuse).
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
from test_llama31_capture import EOS, _provider
from test_observation import QWEN_BUILD, _qwen_result

from sensos_inference.observation import ObservationError, from_llama31, from_qwen35

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


def test_conversion_carries_eos_ids_into_the_provenance(tmp_path: Path) -> None:
    result = _provider(tmp_path).capture_chat(MESSAGES, max_tokens=64, seed=3)
    capture = from_llama31(result, **CONVERT)
    assert capture.provenance.eos_ids == (EOS,)
    assert "provenance.eos_ids" not in capture.unknowns


def test_conversion_rejects_an_eos_id_among_the_generated_tokens(tmp_path: Path) -> None:
    result = _provider(tmp_path).capture_chat(MESSAGES, max_tokens=64, seed=3)
    bad_ids = list(result.token_ids) + [EOS]
    states = np.vstack([result.states, result.states[-1:]])
    bad = replace(result, token_ids=bad_ids, states=states)
    with pytest.raises(ObservationError) as raised:
        from_llama31(bad, **CONVERT)
    assert [issue.code for issue in raised.value.issues] == ["OBS_SRC_EOS"]
    assert raised.value.issues[0].path == "token_ids"


def test_llama_result_without_eos_ids_is_not_refused_and_stays_unknown(tmp_path: Path) -> None:
    result = _provider(tmp_path).capture_chat(MESSAGES, max_tokens=64, seed=3)
    mixed = replace(
        result,
        token_ids=[*result.token_ids, EOS],
        states=np.vstack([result.states, result.states[-1:]]),
        eos_ids=None,
    )
    capture = from_llama31(mixed, **CONVERT)  # not reported: nothing to check against
    assert capture.provenance.eos_ids is None
    assert "provenance.eos_ids" in capture.unknowns
    old = replace(result, eos_ids=None)
    assert from_llama31(old, **CONVERT).provenance.eos_ids is None


def test_llama_empty_eos_ids_is_known_empty(tmp_path: Path) -> None:
    result = _provider(tmp_path).capture_chat(MESSAGES, max_tokens=64, seed=3)
    capture = from_llama31(replace(result, eos_ids=[]), **CONVERT)
    assert capture.provenance.eos_ids == ()
    assert "provenance.eos_ids" not in capture.unknowns


def test_qwen_handling_of_eos_ids_is_as_before(tmp_path: Path) -> None:
    result = _qwen_result(tmp_path, [7, 8, 9, EOS])
    kwargs = {"model_build_id": QWEN_BUILD, "compute_environment": "e"}
    assert from_qwen35(result, **kwargs).provenance.eos_ids == tuple(result.eos_ids)
    assert from_qwen35(replace(result, eos_ids=None), **kwargs).provenance.eos_ids is None
    assert from_qwen35(replace(result, eos_ids=[]), **kwargs).provenance.eos_ids == ()
    mixed = replace(result, token_ids=[7, EOS, 8])
    with pytest.raises(ObservationError) as raised:
        from_qwen35(mixed, **kwargs)
    assert [issue.code for issue in raised.value.issues] == ["OBS_SRC_EOS"]
