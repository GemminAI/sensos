from enum import StrEnum


class AgentProvider(StrEnum):
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    GOOGLE = "google"
    CUSTOM = "custom"


class AgentStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    DEREGISTERED = "deregistered"


class SessionStatus(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    CLOSED = "closed"


class ExperimentStatus(StrEnum):
    OPEN = "open"
    RUNNING = "running"
    COMPLETED = "completed"
    ABORTED = "aborted"


class ExperimentType(StrEnum):
    SEP = "sep"
    SYSID = "sysid"
    CONTROL = "control"
    CUSTOM = "custom"


class ForwardStatus(StrEnum):
    PENDING = "pending"
    QUEUED = "queued"
    FORWARDED = "forwarded"
    SKIPPED = "skipped"
    FAILED = "failed"


class RuntimeEventType(StrEnum):
    SESSION_JOIN = "session.join"
    SESSION_LEAVE = "session.leave"
    NARRATIVE_APPEND = "narrative.append"
    STATE_RAW = "state.raw"
    TRACE_FRAGMENT = "trace.fragment"
    SEP_EXCITATION = "sep.excitation"
    SEP_DISTURBANCE = "sep.disturbance"
    SEP_CONTROL = "sep.control"
    SEP_RAW = "sep.raw"
    HEARTBEAT = "heartbeat"
    ERROR = "error"
    # Runtime Decision Boundary lineage (runtime/services/capability_decision.py).
    # Deliberately NOT added to kernel_gateway._FORWARDED_EVENT_KINDS: a
    # capability request/result is not a Reality-fact observation to send
    # to NVS's /observe -- it is itself a record of a call to NVS's
    # /ports/{id}_Port(/invoke) routes. ForwardWorker correctly SKIPs these
    # (never forwards them a second time to /observe); the Event row is
    # their real, replayable lineage record.
    CAPABILITY_REQUESTED = "capability.requested"
    CAPABILITY_RESULT = "capability.result"


SEP_EVENT_TYPES = frozenset({
    "excitation.step",
    "excitation.pulse",
    "excitation.sweep",
    "excitation.chirp",
    "disturbance.external",
    "disturbance.noise",
    "disturbance.shock",
    "control.setpoint",
    "control.correction",
    "control.inhibit",
    "input.raw",
})

SEP_PREFIX_MAP = {
    "sep.excitation": "excitation.",
    "sep.disturbance": "disturbance.",
    "sep.control": "control.",
    "sep.raw": "input.raw",
}

SCHEMA_VERSION = "nvs.runtime.event.v1"
SEP_VERSION = "nvs.sep.event.v1"
