"""nvs.token-temporal 0.1.0: the payload checks, and the gate_nvs branch."""

from __future__ import annotations

import hashlib
import struct
from typing import Any

import pytest
from contracts import gate, ids
from contracts.gate_nvs import check_nvs_payload
from contracts.hidden_trajectory import HiddenTrajectoryResult
from contracts.jcs import jcs
from contracts.token_temporal import check_token_temporal
from test_hidden_trajectory import BLOBS, MLP, envelope_of, payload_of

TOK = "11" * 32
CHAT = "22" * 32
MODEL = "model-a"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _pack(values: list[int]) -> bytes:
    return struct.pack(f"<{len(values)}q", *values) if values else b""


def _ref(data: bytes, n: int) -> dict[str, Any]:
    digest = _sha(data)
    return {
        "uri": "blob:sha256:" + digest,
        "sha256": digest,
        "media_type": "application/vnd.sensos.ndarray-raw",
        "dtype": "int64",
        "shape": [n],
        "byte_order": "little",
        "order": "C",
        "quantization": None,
        "unit": "token_id",
    }


def _segment_id(tokenizer: str, ids_sha: str, n: int) -> str:
    return _sha(jcs({"domain": "nvs.token-segment/1", "tokenizer_sha256": tokenizer, "ids_sha256": ids_sha, "n": n}))


def _axis_id(segments: list[dict[str, Any]]) -> str:
    body = {"domain": "nvs.token-axis/1", "segments": [{"origin": s["origin"], "segment_id": s["segment_id"]} for s in segments]}
    return _sha(jcs(body))


def _segment(origin: str, values: list[int], tokenizer: str = TOK) -> tuple[dict[str, Any], bytes]:
    data = _pack(values)
    ref = _ref(data, len(values))
    segment = {
        "origin": origin,
        "n": len(values),
        "segment_id": _segment_id(tokenizer, ref["sha256"], len(values)),
        "ids": ref,
    }
    return segment, data


def _shell(payload: dict[str, Any], *, parents: list[dict[str, Any]], schema: tuple[str, str]) -> dict[str, Any]:
    ses = ids.session_id_experiment("sha256:" + "c" * 64, "item-1", "baseline", 0, 1)
    return {
        "contract": {"id": "IC-00", "version": "1.1.0"},
        "content_id": "cnt:" + "0" * 64,
        "artifact_id": "art:" + "0" * 64,
        "kind": "observation",
        "payload_schema": {"id": schema[0], "version": schema[1]},
        "payload": payload,
        "producer": {"name": "sensos-inference", "version": "1.2.3", "build": "adapter-9"},
        "session_id": ses,
        "observation_id": ids.observation_id(ses, 1),
        "event_span": None,
        "space_id": None,
        "parents": parents,
        "policy_refs": [],
        "calibration_ref": None,
        "rule_refs": [],
    }


def _seal(envelope: dict[str, Any], lookup: dict[str, Any]) -> dict[str, Any]:
    sealed = dict(envelope)
    sealed["content_id"] = ids.content_id(sealed, lookup)
    sealed["artifact_id"] = ids.artifact_id(sealed, lookup)
    return sealed


def _world(
    prompt: list[int] | None = None,
    generated: list[int] | None = None,
    *,
    chat: str | None = CHAT,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, bytes]]:
    prompt_ids = [1, 2, 3] if prompt is None else prompt
    gen_ids = [4, 5] if generated is None else generated
    input_seg, input_bytes = _segment("input", prompt_ids)
    gen_seg, gen_bytes = _segment("generated", gen_ids)
    segments = [input_seg, gen_seg]
    parent_payload = {
        "binding": {"n_in": len(prompt_ids), "n_gen": len(gen_ids), "alignment": "decides-next/1"},
        "capture_provenance": {
            "tokenizer_sha256": TOK,
            "chat_template_sha256": chat,
            "prompt_ids_sha256": input_seg["ids"]["sha256"],
            "gen_token_ids_sha256": gen_seg["ids"]["sha256"],
        },
        "model_build_id": MODEL,
    }
    parent = _seal(
        _shell(parent_payload, parents=[], schema=("nvs.hidden-trajectory", "0.1.0")),
        {},
    )
    payload = {
        "axis_id": _axis_id(segments),
        "model_build_id": MODEL,
        "tokenizer_sha256": TOK,
        "chat_template_sha256": chat,
        "segments": segments,
    }
    child = _shell(
        payload,
        parents=[{"role": "source_observation", "ordered": False, "artifact_ids": [parent["artifact_id"]]}],
        schema=("nvs.token-temporal", "0.1.0"),
    )
    lookup = {parent["artifact_id"]: {"content_id": parent["content_id"], "seq": 1, "observation_id": parent["observation_id"]}}
    child = _seal(child, lookup)
    blobs = {input_seg["ids"]["uri"]: input_bytes, gen_seg["ids"]["uri"]: gen_bytes}
    return child, {parent["artifact_id"]: {"envelope": parent}}, blobs


def _codes(envelope: dict[str, Any], stored: dict[str, Any], blobs: dict[str, bytes]) -> list[str]:
    return [v.code for v in check_token_temporal(envelope, stored, blobs)]


def test_a_consistent_artifact_has_no_violation() -> None:
    envelope, stored, blobs = _world()
    assert check_token_temporal(envelope, stored, blobs) == []


def test_a_null_chat_template_matches_the_parent() -> None:
    envelope, stored, blobs = _world(chat=None)
    assert check_token_temporal(envelope, stored, blobs) == []


def test_an_empty_generated_segment_is_accepted() -> None:
    envelope, stored, blobs = _world(generated=[])
    generated = envelope["payload"]["segments"][1]
    assert generated["n"] == 0 and generated["ids"]["shape"] == [0]
    assert blobs[generated["ids"]["uri"]] == b""
    assert check_token_temporal(envelope, stored, blobs) == []


def test_a_schema_failure_is_reported_alone() -> None:
    envelope, stored, blobs = _world()
    envelope["payload"]["extra"] = 1
    found = check_token_temporal(envelope, stored, blobs)
    assert [v.code for v in found] == ["schema"]
    assert found[0].message.startswith("payload/")


@pytest.mark.parametrize(
    ("mutate", "code"),
    [
        ("kind", "token_temporal_kind"),
        ("producer", "token_temporal_producer"),
        ("parents", "token_temporal_parents"),
        ("stored", "token_temporal_parent"),
        ("parent_schema", "token_temporal_parent"),
        ("observation_id", "token_temporal_parent"),
        ("blob", "token_temporal_blob_not_supplied"),
        ("s34", "S34"),
        ("s24", "S24"),
        ("negative", "count_negative"),
        ("n", "token_temporal_n"),
        ("hash", "token_temporal_hash"),
        ("identity", "token_temporal_identity"),
        ("segment_id", "token_temporal_segment_id"),
        ("axis_id", "token_temporal_axis_id"),
    ],
)
def test_one_broken_field_has_its_code(mutate: str, code: str) -> None:
    envelope, stored, blobs = _world()
    segment = envelope["payload"]["segments"][0]
    if mutate == "kind":
        envelope["kind"] = "evidence"
    elif mutate == "producer":
        envelope["producer"]["name"] = "nvs-runtime"
    elif mutate == "parents":
        envelope["parents"][0]["ordered"] = True
    elif mutate == "stored":
        stored = {}
    elif mutate == "parent_schema":
        next(iter(stored.values()))["envelope"]["payload_schema"]["version"] = "0.2.0"
    elif mutate == "observation_id":
        envelope["observation_id"] = ids.observation_id(envelope["session_id"], 2)
    elif mutate == "blob":
        del blobs[segment["ids"]["uri"]]
    elif mutate == "s34":
        segment["ids"]["uri"] = "blob:sha256:" + "ab" * 32
        blobs[segment["ids"]["uri"]] = blobs.pop("blob:sha256:" + segment["ids"]["sha256"])
    elif mutate == "s24":
        blobs[segment["ids"]["uri"]] = _pack([9, 9, 9])
    elif mutate == "negative":
        data = _pack([-1, 2, 3])
        ref = _ref(data, 3)
        segment["ids"] = ref
        segment["segment_id"] = _segment_id(TOK, ref["sha256"], 3)
        envelope["payload"]["axis_id"] = _axis_id(envelope["payload"]["segments"])
        parent = next(iter(stored.values()))["envelope"]["payload"]
        parent["capture_provenance"]["prompt_ids_sha256"] = ref["sha256"]
        blobs = {segment["ids"]["uri"]: data, envelope["payload"]["segments"][1]["ids"]["uri"]: blobs[envelope["payload"]["segments"][1]["ids"]["uri"]]}
    elif mutate == "n":
        next(iter(stored.values()))["envelope"]["payload"]["binding"]["n_in"] = 9
    elif mutate == "hash":
        next(iter(stored.values()))["envelope"]["payload"]["capture_provenance"]["prompt_ids_sha256"] = "cd" * 32
    elif mutate == "identity":
        envelope["payload"]["model_build_id"] = "other-model"
    elif mutate == "segment_id":
        segment["segment_id"] = "ef" * 32
        envelope["payload"]["axis_id"] = _axis_id(envelope["payload"]["segments"])
    elif mutate == "axis_id":
        envelope["payload"]["axis_id"] = "a1" * 32
    found = _codes(envelope, stored, blobs)
    assert found == [code], found


def test_an_unknown_parent_field_is_token_temporal_parent_and_is_not_compared() -> None:
    envelope, stored, blobs = _world()
    parent = next(iter(stored.values()))["envelope"]["payload"]
    parent["binding"]["n_in"] = "unknown"
    found = check_token_temporal(envelope, stored, blobs)
    assert [v.code for v in found] == ["token_temporal_parent"]
    assert "binding.n_in" in found[0].message


def test_gate_nvs_checks_0_1_0_and_rejects_another_version() -> None:
    envelope, stored, blobs = _world()
    assert check_nvs_payload(envelope, stored, blobs) == []
    envelope["payload_schema"] = {"id": "nvs.token-temporal", "version": "0.2.0"}
    found = check_nvs_payload(envelope, stored, blobs)
    assert [(v.code, v.message) for v in found] == [("S39", "unknown payload_schema nvs.token-temporal 0.2.0")]


def test_hidden_trajectory_through_gate_nvs_is_unchanged() -> None:
    result = check_nvs_payload(envelope_of(payload_of(MLP)), None, BLOBS)
    assert isinstance(result, HiddenTrajectoryResult) and result.ok
    assert [item.check for item in result.unverifiable] == ["contract_binding"]
    assert [v.code for v in gate.check_payload(envelope_of(payload_of(MLP)), None, BLOBS)] == ["S39"]
