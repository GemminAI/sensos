"""Harmony response format: extracts the 'final' channel's message.

GPT-OSS models (served locally via MLX, unlike an OpenAI-compatible
server) emit raw Harmony-formatted text: one or more
``<|channel|>{name}<|message|>{content}`` segments -- typically
``analysis`` (chain-of-thought) followed by ``final`` (the actual
answer) -- terminated by ``<|end|>``/``<|return|>`` or end of stream.

This is confirmed directly from the model's own chat template
(``mlx-community/gpt-oss-20b-MXFP4-Q4``'s ``tokenizer_config.json``,
not guessed): "Valid channels: analysis, commentary, final. Channel
must be included for every message.", and the assistant's final turn
is rendered as
``"<|start|>assistant<|channel|>final<|message|>" + message.content +
"<|return|>"``. A real generation on this machine produced exactly that
shape:
``...<|end|><|start|>assistant<|channel|>final<|message|>[{"label":...}]``.

An OpenAI-compatible server (what `VLLMRuntimeBridge` talks to) is
expected to perform this same separation server-side, handing callers
only the final answer via ``choices[0].message.content`` -- the
reasoning/analysis channel is walled off before it ever reaches
`RuntimeBridge`. Running the model in-process via `mlx_lm` bypasses any
such server, so `MLXRuntimeBridge` must do the equivalent extraction
itself before handing content to callers (`LLMAnnotator` and, through
it, `Annotator`/`pipeline`), which have no knowledge of Harmony at all
and expect exactly what `VLLMRuntimeBridge` already provides.

This module never blindly strips ``<|channel|>``: it parses each
channel segment and returns only the ``final`` one's message text. If a
response has no ``final`` channel at all (generation was cut off mid
``analysis``, e.g. by too small a ``max_tokens``), that is reported as
a distinct, typed error rather than silently returning analysis text or
an empty string.
"""

from __future__ import annotations

import re

_CHANNEL_MARKER = "<|channel|>"

_CHANNEL_SEGMENT = re.compile(
    r"<\|channel\|>(?P<channel>[A-Za-z0-9_]+)[^<]*<\|message\|>(?P<message>.*?)"
    r"(?=<\|start\|>|<\|end\|>|<\|return\|>|\Z)",
    re.DOTALL,
)


class HarmonyFormatError(Exception):
    """Raised when a Harmony-formatted response has no 'final' channel."""


def looks_like_harmony(raw: str) -> bool:
    """True if `raw` contains Harmony `<|channel|>` segments at all.

    Used to leave non-Harmony models' output (any other MLX model
    `MLXRuntimeBridge` might be pointed at) completely unaffected --
    this module only ever acts on text that is actually Harmony-shaped.
    """
    return _CHANNEL_MARKER in raw


def extract_final_channel(raw: str) -> str:
    """Return the 'final' channel's message text from a Harmony response.

    Raises `HarmonyFormatError` if no channel segments can be parsed at
    all, or if segments are present but none of them is the 'final'
    channel.
    """
    segments = list(_CHANNEL_SEGMENT.finditer(raw))
    if not segments:
        raise HarmonyFormatError(
            "response contains a '<|channel|>' marker but no parseable "
            "Harmony channel segments"
        )

    final_segments = [m for m in segments if m.group("channel") == "final"]
    if not final_segments:
        channels_seen = ", ".join(dict.fromkeys(m.group("channel") for m in segments))
        raise HarmonyFormatError(
            "no 'final' channel present in Harmony response (channels seen: "
            f"{channels_seen}); generation may have been cut off before reaching "
            "the final channel -- consider increasing max_tokens"
        )

    # Last 'final' segment: a model could in principle emit more than one
    # channel transition; the most recent 'final' message is the answer.
    return final_segments[-1].group("message").strip()
