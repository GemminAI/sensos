"""
sensos.evidence — SPEC-SENSOS-RTV2-001 v1.4 Evidence record (pure schema)
============================================================================

Defines ONLY the type/shape of a per-Port Evidence record, using exclusively
fields that v1.4 explicitly specifies elsewhere in the document. No field is
added that v1.4 does not name. No real Evidence records are constructed or
persisted here — there is no GPT-OSS/EOU data to build one from yet (see
the Reality Audit); this is schema-only, analogous to Parameter Registry
and ObservationState.

Fields, and where each comes from in v1.4:

- eou_spec_identity  : Section 4.1 (seed_set_id, eou_spec_version) — which
                        EOU-128-v1-shaped specification produced the
                        ensemble this record describes.
- state_hash         : Section 2.1 (part of the Canonical State Record
                        triad) — computed by sensos.canonical_hash, kept as
                        an opaque hex string here (this schema does not
                        recompute it).
- var_s              : Section 2.1 Var[S(t)] = tr(Sigma(t)) — computed by
                        sensos.triad.canonical_variance().
- h_comp_raw         : Section 2.1's literal H_comp formula, computed by
                        sensos.triad.raw_spectral_entropy(). NOT the
                        "normalized [0,1]" H-hat — that normalization step
                        is unspecified (see sensos.triad module docstring)
                        and is therefore NOT a field here. Adding a
                        "normalized_h_comp" field now would require
                        guessing that unspecified step; it is deliberately
                        omitted rather than filled with a guess.
- observation_state  : Section 7.2's 5-value ObservationState enum.
- port_id            : which of the 38 fixed Ports (Section 5.1) this
                        record is about.
- attestation_ref    : SEE THE OPEN QUESTION BELOW.
- value_kind wrappers: MeasuredValue / DerivedValue — the type-level
                        measured/derived distinction Section 6 requires of
                        DAK's own output metadata; reused here since
                        Evidence records carry the same distinction.

OPEN QUESTION, not resolved here (flagged, not decided):

v1.4 actually defines TWO different, non-identical attestation-shaped
things, and never states how (or whether) they unify into a single
Evidence-record attestation field:

1. Contract 1's dense_projection.attestation (Section 4.3): model_id,
   model_revision, precision, quantization, seed_set_id,
   projection_algorithm, projection_revision — 7 fields, specific to the
   embedding/projection step.
2. TCK-v2 G0-A's replay-equality tuple (Section 7.4): "model revision,
   runtime version, device class, precision, quantization, seed_set_id,
   sampling parameters" — overlapping but NOT identical (adds runtime
   version + device class + sampling parameters, drops
   projection_algorithm + projection_revision).

Materializing a specific Attestation dataclass here would require silently
choosing one of these two shapes (or inventing a third, merged one) —
none of which v1.4 states. ``attestation_ref`` is therefore kept as an
opaque string (e.g. a hash or label of whichever attestation record is in
play), not a structured object with named sub-fields, until this is
resolved.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeVar

from sensos.observation_state import ObservationState

T = TypeVar("T")


@dataclass(frozen=True)
class MeasuredValue(Generic[T]):
    """
    A value that was directly measured/observed (v1.4 Section 6: DAK
    output must be "measured (measured value), strictly type-level
    distinguished from derived (derived value)"). Wrapping in a distinct
    type makes measured/derived confusion a type error, not just a naming
    convention.
    """

    value: T


@dataclass(frozen=True)
class DerivedValue(Generic[T]):
    """A value computed/derived from other data (v1.4 Section 6). See MeasuredValue."""

    value: T


@dataclass(frozen=True)
class EOUSpecIdentity:
    """Which EOU specification (v1.4 Section 4.1) produced this observation's ensemble."""

    seed_set_id: str
    eou_spec_version: str


@dataclass(frozen=True)
class EvidenceRecord:
    """
    A single Port's Evidence record, per the fields v1.4 explicitly names
    across Sections 2.1, 4.1, 5.1, 6, and 7.2. See module docstring for the
    unresolved attestation-shape question and the omitted
    normalized-H_comp field.
    """

    port_id: str
    eou_spec_identity: EOUSpecIdentity
    state_hash: str
    var_s: DerivedValue[float]
    h_comp_raw: DerivedValue[float]
    observation_state: ObservationState
    attestation_ref: str

    def __post_init__(self) -> None:
        if not self.port_id:
            raise ValueError("port_id must not be empty")
        if not self.state_hash:
            raise ValueError("state_hash must not be empty")
        if len(self.state_hash) != 64 or any(
            c not in "0123456789abcdef" for c in self.state_hash.lower()
        ):
            raise ValueError(f"state_hash must be a 64-char hex SHA-256 digest, got {self.state_hash!r}")
