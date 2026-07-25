"""RFC-HEXT012 §3: Message Router.

Composes the existing ``TopicRouter`` (``runtime/router.py``, untouched)
for topic validation with type-based topic resolution. Per §3 Rule 2, this
module MUST NOT maintain its own ``type -> topic`` table separate from the
one the Processor Pipeline already uses — it imports and reuses
``processors.pipeline.DEFAULT_TOPIC_MAP`` rather than redefining it, so the
two can never drift apart.

Reality check performed during Phase 2 drafting: the reference runtime's
``StreamRuntime`` binds exactly one backend (adapter) for all of its
topics, selected at construction by configuration ("inprocess" or "redis"),
not a different adapter per topic. RFC-HEXT012 §3 Rule 1's "topic-to-adapter
binding" therefore currently degenerates to "topic validation against the
single configured adapter" — this module resolves a type or topic to a
*topic name*; which adapter ultimately serves that topic remains
``StreamRuntime``'s existing, unmodified responsibility.
"""

from __future__ import annotations

from hext_stream.processors.pipeline import DEFAULT_TOPIC_MAP
from hext_stream.runtime.router import TopicRouter


class UnboundTopicError(Exception):
    """RFC-HEXT012 §3 Rule 4: STREAM_ERR_UNBOUND_TOPIC."""

    code = "STREAM_ERR_UNBOUND_TOPIC"


class MessageRouter:
    """RFC-HEXT012 §3: resolves a (type, topic) pair to one validated topic."""

    def __init__(self, topic_router: TopicRouter) -> None:
        self._topic_router = topic_router

    def resolve_topic(self, *, type: str | None = None, topic: str | None = None) -> str:
        """RFC-HEXT012 §3 Rule 2: type-based topic resolution, then Rule 1's
        topic validation.

        If ``topic`` is supplied directly, it is validated as-is (an
        explicit topic always wins — this mirrors how existing callers,
        including CTS, already address topics by name). Otherwise
        ``type`` is resolved through the single shared
        ``DEFAULT_TOPIC_MAP`` the Processor Pipeline already owns.
        """
        resolved = topic if topic is not None else DEFAULT_TOPIC_MAP.get(type or "", type or "")
        try:
            return self._topic_router.validate(resolved)
        except ValueError as exc:
            raise UnboundTopicError(str(exc)) from exc

    def register(self, topic: str) -> None:
        self._topic_router.register(topic)

    @property
    def topics(self) -> list[str]:
        return self._topic_router.topics
