"""Generate the nvs.hidden-trajectory 0.1.0 payload vectors
(docs/architecture/contracts/nvs/vectors/hidden-trajectory-payload.json).

Run:  python tools/contracts/make_vectors_hidden_trajectory.py  (from the repository root)

Separate from ``make_vectors.py`` and the IC-02 generators; it imports only the schema loader. Output is
deterministic (indent=1, sorted keys, ensure_ascii=False, trailing newline, like make_vectors_window_rows.py).

Every ``expect.path`` below is written by hand from design U5 v0.2 section 3 (the schema's first error, as
``check_payload`` would report it: errors sorted by ``list(absolute_path)``, the first one, its path joined by
``/``; an error on the payload itself such as a missing field has the empty path ""). The generator then runs
the schema and refuses to write the file if one case disagrees with its hand-written expectation.

``points`` is T=3, D=4 float32 (0.0 .. 11.0, 48 bytes); ``token_index`` is int64 [0, 1, 2]; both are in
``blobs`` (uri -> hex). Only the schema is replayed here; the Gate's meaning checks (HT-04 .. HT-17) are U5-4.
"""

from __future__ import annotations

import hashlib
import json
import struct
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from contracts.hidden_trajectory_registry import hidden_trajectory_validator

SCHEMA = "nvs/hidden-trajectory.schema.json"
OUT = (
    Path(__file__).resolve().parents[2]
    / "docs/architecture/contracts/nvs/vectors/hidden-trajectory-payload.json"
)
T = 3
D = 4
BLOBS: dict[str, bytes] = {}

REQUIRED = (
    "source",
    "position",
    "point",
    "kind",
    "layer",
    "length",
    "dimension",
    "points",
    "token_index",
    "raw_ref",
    "row_rule",
    "binding",
    "final_norm_applied",
    "state_dtype",
    "model_build_id",
    "compute_environment",
    "policy",
    "capture_provenance",
    "contract_ref",
    "unknowns",
)


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _blob(data: bytes) -> str:
    BLOBS["blob:sha256:" + sha(data)] = data
    return "blob:sha256:" + sha(data)


POINTS_DATA = struct.pack(f"<{T * D}f", *[float(i) for i in range(T * D)])
INDEX_DATA = struct.pack(f"<{T}q", *range(T))
POINTS_SHA = sha(POINTS_DATA)
POLICY_NAME = "capture-all-rows/1"


def base(point: str = "mlp_out:15") -> dict[str, Any]:
    """Qwen3.5 mlp_out:15 (an accept case)."""
    kind, _, layer = point.partition(":")
    final = point == "final_norm"
    return {
        "source": "T-hid",
        "position": "final_norm" if final else f"L{layer}.{kind}",
        "point": point,
        "kind": "final_norm" if final else kind,
        "layer": "final_norm" if final else int(layer),
        "length": T,
        "dimension": D,
        "points": {
            "uri": _blob(POINTS_DATA),
            "sha256": POINTS_SHA,
            "media_type": "application/vnd.sensos.ndarray-raw",
            "dtype": "float32",
            "shape": [T, D],
            "byte_order": "little",
            "order": "C",
            "unit": "activation",
        },
        "token_index": {
            "uri": _blob(INDEX_DATA),
            "sha256": sha(INDEX_DATA),
            "media_type": "application/vnd.sensos.ndarray-raw",
            "dtype": "int64",
            "shape": [T],
            "byte_order": "little",
            "order": "C",
            "quantization": None,
            "unit": "token_position",
        },
        "raw_ref": {"trajectory_id": POINTS_SHA, "copied": False},
        "row_rule": (
            "llama31-mlx-final-norm/1"
            if final
            else f"qwen35-mlx-{kind.replace('_', '-')}/1"
        ),
        "binding": {
            "alignment": "decides-next/1",
            "n_in": 5,
            "n_gen": T,
            "finish_reason": "eos",
        },
        "final_norm_applied": final,
        "state_dtype": "float16",
        "model_build_id": "mlx-community/Qwen3.5-9B-4bit@rev1",
        "compute_environment": "apple-m3-max/mlx-0.31",
        "policy": {"name": POLICY_NAME, "sha256": sha(POLICY_NAME.encode())},
        "capture_provenance": {
            "weights_sha256": sha(b"weights"),
            "tokenizer_sha256": sha(b"tokenizer"),
            "chat_template_sha256": sha(b"chat template"),
            "prompt_ids_sha256": sha(b"prompt ids"),
            "gen_token_ids_sha256": sha(b"gen token ids"),
            "capture": {
                "package": "sensos-inference",
                "version": "0.1.0",
                "adapter": "mlx-qwen35",
            },
            "runtime": {"backend": "mlx", "version": "0.31.0"},
            "model_source": None,
        },
        "contract_ref": {
            "name": "RawObservationContract",
            "version": 2,
            "contract_sha256": sha(b"contract v2"),
        },
        "unknowns": [],
    }


def llama_final_norm() -> dict[str, Any]:
    p = base("final_norm")
    p["model_build_id"] = "mlx-community/Llama-3.1-8B-4bit@rev1"
    return p


def block_out_15() -> dict[str, Any]:
    return base("block_out:15")


def mlp_out_15() -> dict[str, Any]:
    return base("mlp_out:15")


def partly_unknown() -> dict[str, Any]:
    p = base()
    p["capture_provenance"]["weights_sha256"] = "unknown"
    p["state_dtype"] = "unknown"
    p["unknowns"] = [
        {"field": "/capture_provenance/weights_sha256", "reason": "not_recorded"},
        {"field": "/state_dtype", "reason": "unknown"},
    ]
    return p


def contract_null() -> dict[str, Any]:
    p = base()
    p["contract_ref"] = None
    return p


def not_applicable_template() -> dict[str, Any]:
    p = base()
    p["capture_provenance"]["chat_template_sha256"] = "not_applicable"
    return p


def _walk(p: dict[str, Any], dotted: str) -> tuple[Any, str]:
    parts = dotted.split(".")
    cur: Any = p
    for part in parts[:-1]:
        cur = cur[int(part)] if isinstance(cur, list) else cur[part]
    return cur, parts[-1]


def put(dotted: str, value: Any) -> Callable[[dict[str, Any]], None]:
    def f(p: dict[str, Any]) -> None:
        cur, last = _walk(p, dotted)
        cur[int(last) if isinstance(cur, list) else last] = value

    return f


def drop(dotted: str) -> Callable[[dict[str, Any]], None]:
    def f(p: dict[str, Any]) -> None:
        cur, last = _walk(p, dotted)
        del cur[last]

    return f


def main() -> None:
    check = hidden_trajectory_validator(SCHEMA)
    cases: list[dict[str, Any]] = []

    def first_path(payload: dict[str, Any]) -> str | None:
        errors = sorted(check.iter_errors(payload), key=lambda e: list(e.absolute_path))
        return "/".join(str(x) for x in errors[0].absolute_path) if errors else None

    def accept(case_id: str, description: str, payload: dict[str, Any]) -> None:
        found = first_path(payload)
        if found is not None:
            raise AssertionError(
                f"{case_id}: expected accept, schema reports {found!r}"
            )
        cases.append(
            {
                "id": case_id,
                "description": description,
                "payload": payload,
                "expect": {"result": "accept", "path": None},
            }
        )

    def reject(
        case_id: str,
        description: str,
        mutate: Callable[[dict[str, Any]], None],
        path: str,
        start: Callable[[], dict[str, Any]] = base,
    ) -> None:
        payload = start()
        mutate(payload)
        found = first_path(payload)
        if found != path:
            raise AssertionError(
                f"{case_id}: expected path {path!r}, schema reports {found!r}"
            )
        cases.append(
            {
                "id": case_id,
                "description": description,
                "payload": payload,
                "expect": {"result": "reject", "path": path},
            }
        )

    # ------------------------------------------------------------------ accept
    accept(
        "accept-llama-final-norm",
        'Llama 系の final_norm（row_rule llama31-mlx-final-norm/1、layer "final_norm"、final_norm_applied true）',
        llama_final_norm(),
    )
    accept(
        "accept-qwen35-block-out-15",
        "Qwen3.5 の block_out:15（layer 15、qwen35-mlx-block-out/1）",
        block_out_15(),
    )
    accept(
        "accept-qwen35-mlp-out-15",
        "Qwen3.5 の mlp_out:15（final_norm_applied false）",
        mlp_out_15(),
    )
    accept(
        "accept-partly-unknown-provenance",
        '来歴の一部（weights_sha256・state_dtype）が "unknown" で、unknowns に載っている',
        partly_unknown(),
    )
    accept("accept-contract-ref-null", "contract_ref が null", contract_null())
    accept(
        "accept-chat-template-not-applicable",
        'chat_template_sha256 が "not_applicable"（unknowns には載せない）',
        not_applicable_template(),
    )
    p = base()
    p["capture_provenance"]["runtime"] = {"backend": "unknown"}
    accept(
        "accept-runtime-backend-unknown", 'runtime.backend が "unknown"（文字列）', p
    )
    p = base("block_out:0")
    accept("accept-layer-zero", "layer 0（整数の下限）", p)
    p = base()
    p["binding"]["finish_reason"] = "length"
    accept("accept-finish-reason-length", 'finish_reason "length"', p)

    # ------------------------------------------------- reject: a required field is missing
    for name in REQUIRED:
        reject(f"reject-missing-{name}", f"必須の欄 {name} が欠ける", drop(name), "")

    # ----------------------------------------------------------- reject: extra fields
    reject(
        "reject-extra-dimensions",
        "dimensions（複数形）の欄（親 v0.1 の名前。dimension に直す）",
        put("dimensions", [D]),
        "",
    )
    reject(
        "reject-extra-top-level",
        "payload の直下に余計な欄",
        put("space_id", "hid:" + "0" * 64),
        "",
    )
    reject(
        "reject-extra-binding",
        "binding の中に余計な欄",
        put("binding.extra", 1),
        "binding",
    )
    reject(
        "reject-extra-raw-ref",
        "raw_ref の中に余計な欄（U4 の format など）",
        put("raw_ref.format", "TRJ_V2"),
        "raw_ref",
    )
    reject(
        "reject-extra-policy", "policy の中に余計な欄", put("policy.extra", 1), "policy"
    )
    reject(
        "reject-extra-capture-provenance",
        "capture_provenance の中に余計な欄",
        put("capture_provenance.extra", 1),
        "capture_provenance",
    )
    reject(
        "reject-extra-contract-ref",
        "contract_ref の中に余計な欄",
        put("contract_ref.extra", 1),
        "contract_ref",
    )
    reject(
        "reject-extra-capture",
        "capture の中に余計な欄",
        put("capture_provenance.capture.extra", "x"),
        "capture_provenance/capture",
    )
    reject(
        "reject-extra-unknowns-item",
        "unknowns の要素に余計な欄",
        put("unknowns", [{"field": "/state_dtype", "reason": "unknown", "extra": 1}]),
        "unknowns/0",
    )

    # -------------------------------------------------------------------- reject: layer
    for suffix, value, why in (
        ("digit-string", "15", '数字だけの文字列（15 と "15" は別物。D-179）'),
        ("bool", True, "真偽"),
        ("negative", -1, "負の数"),
        ("kind-name", "mlp_out", "kind の名前"),
        ("null", None, "null"),
        ("fraction", 15.5, "小数"),
    ):
        reject(
            f"reject-layer-{suffix}", f"layer が {why}", put("layer", value), "layer"
        )

    # ---------------------------------- reject: a missing-value word where none is allowed
    for field, path in (
        ("row_rule", "row_rule"),
        ("model_build_id", "model_build_id"),
        ("compute_environment", "compute_environment"),
        ("dimension", "dimension"),
        ("length", "length"),
        ("final_norm_applied", "final_norm_applied"),
        ("binding.n_in", "binding/n_in"),
        ("binding.alignment", "binding/alignment"),
        ("raw_ref.trajectory_id", "raw_ref/trajectory_id"),
    ):
        reject(
            f"reject-unknown-in-{field.replace('.', '-')}",
            f'{field} に "unknown"（欠損の語を書けない欄）',
            put(field, "unknown"),
            path,
        )
    reject(
        "reject-not-applicable-in-weights-sha256",
        'weights_sha256 に "not_applicable"（chat_template_sha256 だけ）',
        put("capture_provenance.weights_sha256", "not_applicable"),
        "capture_provenance/weights_sha256",
    )
    reject(
        "reject-not-applicable-in-state-dtype",
        'state_dtype に "not_applicable"',
        put("state_dtype", "not_applicable"),
        "state_dtype",
    )
    reject(
        "reject-not-applicable-in-prompt-ids",
        'prompt_ids_sha256 に "not_applicable"',
        put("capture_provenance.prompt_ids_sha256", "not_applicable"),
        "capture_provenance/prompt_ids_sha256",
    )

    # ---------------------------------------------------------------- reject: contract_ref
    reject(
        "reject-contract-version-1",
        "contract_ref.version が 1",
        put("contract_ref.version", 1),
        "contract_ref",
    )
    reject(
        "reject-contract-version-3",
        "contract_ref.version が 3",
        put("contract_ref.version", 3),
        "contract_ref",
    )
    reject(
        "reject-contract-version-string",
        'contract_ref.version が文字列 "2"',
        put("contract_ref.version", "2"),
        "contract_ref",
    )
    reject(
        "reject-contract-name",
        "contract_ref.name が違う",
        put("contract_ref.name", "RawObservationContractV2"),
        "contract_ref",
    )
    reject(
        "reject-contract-sha256-short",
        "contract_ref.contract_sha256 が短い",
        put("contract_ref.contract_sha256", "a" * 63),
        "contract_ref",
    )
    for name in ("name", "version", "contract_sha256"):
        reject(
            f"reject-contract-missing-{name}",
            f"contract_ref の {name} が欠ける",
            drop(f"contract_ref.{name}"),
            "contract_ref",
        )

    # ------------------------------------------------- reject: source, kind, point, position
    reject("reject-source-t-tok", 'source が "T-tok"', put("source", "T-tok"), "source")
    reject(
        "reject-kind-interpretation",
        'kind が "interpretation"',
        put("kind", "interpretation"),
        "kind",
    )
    reject(
        "reject-point-leading-zero",
        "point が mlp_out:015（先頭の 0）",
        put("point", "mlp_out:015"),
        "point",
    )
    reject(
        "reject-point-no-layer",
        "point が block_out（層なし）",
        put("point", "block_out"),
        "point",
    )
    reject(
        "reject-position-bad-form",
        "position の形が違う（L15.mlp）",
        put("position", "L15.mlp"),
        "position",
    )
    reject(
        "reject-position-leading-zero",
        "position が L015.mlp_out",
        put("position", "L015.mlp_out"),
        "position",
    )
    reject("reject-position-empty", "position が空", put("position", ""), "position")

    # -------------------------------------------------------------------- reject: row_rule
    reject(
        "reject-row-rule-window",
        "row_rule が窓の派生の形（…+rows0+128/1）",
        put("row_rule", "qwen35-mlx-mlp-out/1+rows0+128/1"),
        "row_rule",
    )
    reject(
        "reject-row-rule-description",
        "row_rule が説明文",
        put("row_rule", "all rows of the mlp out"),
        "row_rule",
    )
    reject(
        "reject-row-rule-no-kind-slug",
        "row_rule に種類のスラッグが無い（qwen35-mlx/1）",
        put("row_rule", "qwen35-mlx/1"),
        "row_rule",
    )
    reject(
        "reject-row-rule-version-zero",
        "row_rule の版が 0",
        put("row_rule", "qwen35-mlx-mlp-out/0"),
        "row_rule",
    )
    reject(
        "reject-row-rule-uppercase",
        "row_rule に大文字",
        put("row_rule", "Qwen35-mlx-mlp-out/1"),
        "row_rule",
    )

    # ------------------------------------------------------- reject: dimension, length
    reject("reject-dimension-zero", "dimension が 0", put("dimension", 0), "dimension")
    reject(
        "reject-dimension-65536",
        "dimension が 65536",
        put("dimension", 65536),
        "dimension",
    )
    reject(
        "reject-dimension-bool", "dimension が真偽", put("dimension", True), "dimension"
    )
    reject(
        "reject-dimension-fraction",
        "dimension が小数 4.5",
        put("dimension", 4.5),
        "dimension",
    )
    reject("reject-length-zero", "length が 0", put("length", 0), "length")
    reject("reject-length-string", "length が文字列", put("length", "3"), "length")

    # ------------------------------------------------------------------ reject: binding
    reject(
        "reject-alignment-other",
        "binding.alignment が別の値",
        put("binding.alignment", "decides-next/2"),
        "binding/alignment",
    )
    reject(
        "reject-finish-reason-other",
        "binding.finish_reason が別の値",
        put("binding.finish_reason", "stop"),
        "binding/finish_reason",
    )
    reject(
        "reject-n-gen-zero",
        "binding.n_gen が 0",
        put("binding.n_gen", 0),
        "binding/n_gen",
    )
    reject(
        "reject-n-in-zero", "binding.n_in が 0", put("binding.n_in", 0), "binding/n_in"
    )
    for name in ("alignment", "n_in", "n_gen", "finish_reason"):
        reject(
            f"reject-binding-missing-{name}",
            f"binding の {name} が欠ける",
            drop(f"binding.{name}"),
            "binding",
        )

    # ---------------------------------------------------- reject: points and token_index
    reject(
        "reject-points-dtype-float64",
        "points.dtype が float64（float32 Blob の $ref が効いている）",
        put("points.dtype", "float64"),
        "points/dtype",
    )
    reject(
        "reject-points-shape-zero",
        "points.shape に 0",
        put("points.shape", [0, D]),
        "points/shape/0",
    )
    reject(
        "reject-points-missing-unit",
        "points の欄（unit）が欠ける",
        drop("points.unit"),
        "points",
    )
    reject(
        "reject-points-extra-quantization",
        "points に余計な欄（quantization）",
        put("points.quantization", None),
        "points",
    )
    reject(
        "reject-points-missing-sha256",
        "points の sha256 が欠ける",
        drop("points.sha256"),
        "points",
    )
    reject(
        "reject-token-index-dtype-float64",
        "token_index.dtype が float64（個数の Blob ではない）",
        put("token_index.dtype", "float64"),
        "token_index/dtype",
    )
    reject(
        "reject-token-index-quantization",
        "token_index.quantization が null でない",
        put(
            "token_index.quantization",
            {
                "quantum": {"base": 2, "exponent": -30},
                "rounding": "ties-to-even",
                "tolerance_quanta": 1,
            },
        ),
        "token_index/quantization",
    )
    reject(
        "reject-token-index-shape-2d",
        "token_index.shape が 2 次元",
        put("token_index.shape", [T, 1]),
        "token_index/shape",
    )
    reject(
        "reject-token-index-shape-zero",
        "token_index.shape が [0]",
        put("token_index.shape", [0]),
        "token_index/shape/0",
    )

    # ------------------------------------------------- reject: the remaining small fields
    reject(
        "reject-policy-sha256-short",
        "policy.sha256 が短い",
        put("policy.sha256", "a" * 63),
        "policy/sha256",
    )
    reject(
        "reject-policy-name-empty",
        "policy.name が空",
        put("policy.name", ""),
        "policy/name",
    )
    reject(
        "reject-raw-ref-uppercase",
        "raw_ref.trajectory_id が大文字",
        put("raw_ref.trajectory_id", POINTS_SHA.upper()),
        "raw_ref/trajectory_id",
    )
    reject(
        "reject-raw-ref-copied-string",
        "raw_ref.copied が文字列",
        put("raw_ref.copied", "false"),
        "raw_ref/copied",
    )
    reject(
        "reject-model-source-not-null",
        "capture_provenance.model_source が null でない",
        put("capture_provenance.model_source", "hf://x"),
        "capture_provenance/model_source",
    )
    reject(
        "reject-unknowns-bad-reason",
        "unknowns の reason が不正",
        put("unknowns", [{"field": "/state_dtype", "reason": "forgotten"}]),
        "unknowns/0/reason",
    )
    reject(
        "reject-unknowns-field-no-slash",
        "unknowns の field が / で始まらない",
        put("unknowns", [{"field": "state_dtype", "reason": "unknown"}]),
        "unknowns/0/field",
    )
    reject(
        "reject-unknowns-not-array",
        "unknowns が配列でない",
        put("unknowns", None),
        "unknowns",
    )
    reject(
        "reject-state-dtype-empty",
        "state_dtype が空",
        put("state_dtype", ""),
        "state_dtype",
    )
    reject(
        "reject-model-build-id-space",
        "model_build_id に空白",
        put("model_build_id", "model build"),
        "model_build_id",
    )
    reject(
        "reject-compute-environment-empty",
        "compute_environment が空",
        put("compute_environment", ""),
        "compute_environment",
    )
    reject(
        "reject-weights-sha256-uppercase",
        "weights_sha256 が大文字",
        put("capture_provenance.weights_sha256", "A" * 64),
        "capture_provenance/weights_sha256",
    )
    reject(
        "reject-chat-template-other-word",
        "chat_template_sha256 が別の語",
        put("capture_provenance.chat_template_sha256", "none"),
        "capture_provenance/chat_template_sha256",
    )
    reject(
        "reject-capture-version-empty",
        "capture.version が空",
        put("capture_provenance.capture.version", ""),
        "capture_provenance/capture/version",
    )
    reject(
        "reject-capture-missing-adapter",
        "capture.adapter が欠ける",
        drop("capture_provenance.capture.adapter"),
        "capture_provenance/capture",
    )
    reject(
        "reject-runtime-missing-backend",
        "runtime.backend が欠ける",
        put("capture_provenance.runtime", {"version": "0.31.0"}),
        "capture_provenance/runtime",
    )
    reject(
        "reject-runtime-non-string",
        "runtime の値が文字列でない",
        put("capture_provenance.runtime.version", 31),
        "capture_provenance/runtime/version",
    )
    reject(
        "reject-capture-provenance-missing-weights",
        "capture_provenance の weights_sha256 が欠ける",
        drop("capture_provenance.weights_sha256"),
        "capture_provenance",
    )

    # Floats: the schema alone accepts 15.0 / 4.0 as integers (JSON Schema 2020-12 treats 1.0 as an integer).
    # The strict JSON loader (strict_load.py) refuses every float before a payload reaches the schema, so these
    # are not schema rejects. Kept apart, with the loader's verdict, so nobody counts them as schema vectors.
    floats = []
    for fid, field, value in (
        ("layer-15-point-0", "layer", 15.0),
        ("dimension-4-point-0", "dimension", 4.0),
    ):
        payload = base()
        payload[field] = value
        floats.append(
            {
                "id": f"float-{fid}",
                "description": f"{field} が {value!r}（スキーマは整数として受理する。strict_load が先に拒否する）",
                "payload": payload,
                "expect": {"schema": "accept", "strict_load": "reject"},
            }
        )

    doc = {
        "format": "hidden-trajectory-payload/1",
        "schema": SCHEMA,
        "rule": "hidden_trajectory_validator('nvs/hidden-trajectory.schema.json') on payload: expect.result accept (no error) or reject, and expect.path = the first error's absolute_path joined by '/' (sorted by list(absolute_path); \"\" for an error on the payload itself). blobs: uri -> hex of the Blob bytes (points T=3 x D=4 float32; token_index int64 [0,1,2]); the schema does not read them. float_cases are not schema rejects (see the generator).",
        "status": "草案 (nvs.hidden-trajectory 0.1.0。Gate の意味の検査 HT-04〜HT-17 は U5-4)",
        "blobs": {u: d.hex() for u, d in sorted(BLOBS.items())},
        "cases": cases,
        "float_cases": floats,
    }
    OUT.write_text(
        json.dumps(doc, indent=1, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    acc = sum(c["expect"]["result"] == "accept" for c in cases)
    print(
        f"{len(cases)} cases, {acc} accept, {len(cases) - acc} reject, {len(floats)} float cases -> {OUT}"
    )


if __name__ == "__main__":
    main()
