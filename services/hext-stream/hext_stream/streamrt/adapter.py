"""RFC-HEXT012 §2: Transport Adapter Contract.

The reference runtime's existing ``StreamBackend`` ABC
(``backend/backend_interface.py``) already implements the full eight-method
contract this section requires — ``publish``, ``subscribe``, ``unsubscribe``,
``replay``, ``history``, ``health``, ``queue_depth``, ``close`` — confirmed
against the real interface during Phase 2 drafting (see RFC-HEXT012's
amendment note). This module does not redefine that contract; it re-exports
it under the RFC's own terminology so Phase 2 code can depend on
"the Stream Adapter contract" by name without a second, parallel interface.
"""

from __future__ import annotations

from hext_stream.backend.backend_interface import (
    Callback,
    StreamBackend,
    SubscriptionHandle,
)

# RFC-HEXT012 §2: "Stream Adapter" is this document's name for what the
# reference runtime already calls StreamBackend. Same class, same contract.
StreamAdapter = StreamBackend

__all__ = ["StreamAdapter", "StreamBackend", "SubscriptionHandle", "Callback"]
