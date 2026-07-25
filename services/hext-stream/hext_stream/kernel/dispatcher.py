"""RFC-HEXT011 §4: Processor Dispatcher.

Per §4.5's "minimal conformant implementation" clause, the existing
``ProcessorRegistry``/``Pipeline`` synchronous, single-threaded,
dispatch-by-``event.type`` mechanism already satisfies this section's
routing requirement and is reused, not rewritten (``processors/registry.py``
and ``processors/pipeline.py`` are untouched by this module).

This module adds only what §4.3 requires and the existing registry does not
provide: rejecting an object whose ``type`` is neither ``"observation"`` nor
one of the six fixed ``processor.*`` tags, when it is presented at the
kernel's *strict* entry point. It does not change ``ProcessorRegistry``'s
own permissive ``dispatch()`` (many legitimate object types — e.g.
``diagnostic``, ``metrics``, ``surface`` — are correctly published without
ever being intended for Processor Pipeline dispatch at all; treating every
unregistered type as an error there would be wrong, not conformant).
``ProcessorDispatcher.dispatch_strict`` is for kernel-driven code paths that
specifically mean to enter the Processor Pipeline, where §4.1's fixed
routing table is the actual contract in force.
"""

from __future__ import annotations

from hext_stream.processors.registry import ProcessorRegistry
from hext_stream.schema.base import HextObject

# RFC-HEXT011 §4.1: the fixed routing table — the six Processor Pipeline
# stage type tags of RFC-HEXT004 §7, plus the "observation" pipeline entry
# point of RFC-HEXT001 §7.1 / RFC-HEXT004 §7.1's diagram.
ENTRY_POINT_TYPES: frozenset[str] = frozenset(
    {
        "observation",
        "processor.trajectory",
        "processor.flow",
        "processor.hom",
        "processor.diagram",
        "processor.rewrite",
        "processor.controller",
    }
)


class KernelUnroutableTypeError(Exception):
    """RFC-HEXT011 §4.3: KERNEL_ERR_UNROUTABLE_TYPE."""

    code = "KERNEL_ERR_UNROUTABLE_TYPE"


class ProcessorDispatcher:
    """RFC-HEXT011 §4: strict entry-point dispatch, composed over ``ProcessorRegistry``."""

    def __init__(self, registry: ProcessorRegistry) -> None:
        self._registry = registry

    def dispatch_strict(self, event: HextObject) -> list[HextObject]:
        """Dispatch an object presented at the Processor Pipeline's own
        entry boundary. Raises ``KernelUnroutableTypeError`` per §4.3 if
        ``event.type`` is not one of §4.1's fixed entry-point types.
        Objects of any other type are not this dispatcher's concern — see
        ``ProcessorRegistry.dispatch`` for the runtime's general,
        permissive event-type dispatch used elsewhere.
        """
        if event.type not in ENTRY_POINT_TYPES:
            raise KernelUnroutableTypeError(
                f"{event.type!r} is not a Processor Pipeline entry-point type "
                f"(expected one of {sorted(ENTRY_POINT_TYPES)})"
            )
        return self._registry.dispatch(event)
