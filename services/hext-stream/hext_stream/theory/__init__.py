"""RFC-HEXT016 Theory Runtime.

`TheoryContext`, `TheoryConfig`, `TheoryRegistry`, `TheoryLoader`,
`TheoryExecutor`, `TheoryResult`, `TheoryManager`, and the shared
`TheorySwitchingNotImplementedError`. Theory Replay (§7) and Theory Diff
(§8) are specified here but implemented in `hext_stream/trajectory/`
(`ReplayHandle.run`, `TheoryDiff`) — this package's own dependency
direction (§1.1) forbids importing Trajectory Runtime types such as
`ReplayResult` from here.
"""

from __future__ import annotations

from hext_stream.theory.config import TheoryConfig
from hext_stream.theory.context import TheoryContext
from hext_stream.theory.errors import TheorySwitchingNotImplementedError
from hext_stream.theory.executor import TheoryExecutor, TheoryResult
from hext_stream.theory.loader import (
    CircularParentError,
    InvalidCoefficientTypeError,
    TheoryLoader,
    TheoryLoaderError,
    UnknownCoefficientError,
    UnknownParentError,
)
from hext_stream.theory.manager import TheoryManager, TheoryNotRegisteredError
from hext_stream.theory.registry import TheoryRegistry

__all__ = [
    "TheoryConfig",
    "TheoryContext",
    "TheorySwitchingNotImplementedError",
    "TheoryLoader",
    "TheoryLoaderError",
    "UnknownCoefficientError",
    "InvalidCoefficientTypeError",
    "UnknownParentError",
    "CircularParentError",
    "TheoryExecutor",
    "TheoryResult",
    "TheoryManager",
    "TheoryNotRegisteredError",
    "TheoryRegistry",
]
