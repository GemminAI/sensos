from dataclasses import dataclass

import numpy as np

from sensos_inference import EOS_MISSING, GENERATE_FAILED, LENGTH_LIMIT, LOAD_FAILED
from sensos_inference.providers.llama31_mlx import Llama31MLXProvider


@dataclass
class _Resp:
    token: int
    finish_reason: str | None = None


class _Tok:
    chat_template = "{{ messages }}"

    def __init__(self, eos=(128001, 128008, 128009)):
        self.eos_token_ids = set(eos)

    def apply_chat_template(self, messages, add_generation_prompt, tokenize):
        return [1, 2, 3]

    def decode(self, ids):
        return " ".join(str(i) for i in ids)


def _provider(stream, tok=None, loader=None):
    return Llama31MLXProvider(
        revision="r1",
        loader=loader or (lambda model_id: (object(), tok or _Tok())),
        stream=stream,
    )


def test_eos_finish_records_everything():
    def stream(model, tok, prompt, max_tokens, sampler):
        assert prompt == [1, 2, 3]
        for t in (10, 11, 128009):
            yield _Resp(t)

    r = _provider(stream).generate_chat([{"role": "user", "content": "hi"}], max_tokens=8, seed=3)
    assert r.ok and r.finish_reason == "eos" and r.failure_kind is None
    assert r.token_ids == [10, 11] and r.completion_tokens == 2 and r.prompt_tokens == 3
    assert r.model_ref == "mlx-community/Meta-Llama-3.1-8B-Instruct-4bit" and r.revision == "r1"
    assert r.sampler["order"] == ["temperature", "top_k", "top_p"] and r.sampler["seed"] == 3
    assert r.sampler["top_k"] == 50 and r.sampler["top_p"] == 0.95 and r.sampler["temperature"] == 0.7
    assert len(r.chat_template_sha256 or "") == 64
    assert r.load_seconds is not None and r.generate_seconds is not None


def test_length_limit_is_distinguished():
    def stream(model, tok, prompt, max_tokens, sampler):
        for i in range(max_tokens):
            yield _Resp(10 + i, "length" if i == max_tokens - 1 else None)

    r = _provider(stream).generate_chat([{"role": "user", "content": "x"}], max_tokens=4)
    assert not r.ok and r.failure_kind == LENGTH_LIMIT and r.finish_reason == "length"
    assert r.completion_tokens == 4


def test_eos_missing_when_stream_ends_early_without_eos():
    def stream(model, tok, prompt, max_tokens, sampler):
        yield _Resp(10)

    r = _provider(stream).generate_chat([{"role": "user", "content": "x"}], max_tokens=4)
    assert not r.ok and r.failure_kind == EOS_MISSING


def test_no_eos_ids_configured():
    r = _provider(lambda *a, **k: iter(()), tok=_Tok(eos=())).generate_chat(
        [{"role": "user", "content": "x"}]
    )
    assert not r.ok and r.failure_kind == EOS_MISSING


def test_load_failure():
    def bad(model_id):
        raise OSError("no weights")

    r = _provider(lambda *a, **k: iter(()), loader=bad).generate_chat([{"role": "user", "content": "x"}])
    assert not r.ok and r.failure_kind == LOAD_FAILED and "no weights" in (r.error or "")
    again = _provider(lambda *a, **k: iter(()), loader=bad)
    again.generate_chat([{"role": "user", "content": "x"}])
    assert again.generate_chat([{"role": "user", "content": "y"}]).failure_kind == LOAD_FAILED


def test_generation_exception():
    def stream(model, tok, prompt, max_tokens, sampler):
        raise RuntimeError("boom")
        yield  # pragma: no cover

    r = _provider(stream).generate_chat([{"role": "user", "content": "x"}])
    assert not r.ok and r.failure_kind == GENERATE_FAILED


def test_existing_generate_contract_is_kept():
    def stream(model, tok, prompt, max_tokens, sampler):
        yield _Resp(128009)

    r = _provider(stream).generate("hello", max_tokens=5)
    assert r.ok and r.prompt_chars == 5 and r.max_tokens == 5


def test_sampler_is_passed_through_and_seeded():
    seen = {}

    def stream(model, tok, prompt, max_tokens, sampler):
        seen["sampler"] = sampler
        yield _Resp(128009)

    _provider(stream).generate_chat([{"role": "user", "content": "x"}], seed=9)
    logits = np.log(np.array([0.5, 0.5]))
    assert seen["sampler"](logits) in (0, 1)
