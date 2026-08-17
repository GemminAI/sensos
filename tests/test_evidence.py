"""
Tests for sensos.evidence — a pure schema, not a real-data producer. All
values used below are synthetic placeholders assembled from
sensos.triad/sensos.canonical_hash's own pure-function outputs on synthetic
numeric/dict inputs; none represent a real GPT-OSS/EOU observation.
"""

from __future__ import annotations

import dataclasses

import numpy as np
import pytest
from sensos.canonical_hash import canonical_tag_hash
from sensos.evidence import DerivedValue, EOUSpecIdentity, EvidenceRecord, MeasuredValue
from sensos.observation_state import ObservationState
from sensos.triad import canonical_variance, raw_spectral_entropy


def test_evidence_record_has_exactly_the_specified_fields():
    field_names = {f.name for f in dataclasses.fields(EvidenceRecord)}
    assert field_names == {
        "port_id",
        "eou_spec_identity",
        "state_hash",
        "var_s",
        "h_comp_raw",
        "observation_state",
        "attestation_ref",
    }


def test_no_normalized_h_comp_field_present():
    # Deliberate omission -- see module docstring / sensos.triad. Asserting
    # its absence here so a future edit can't silently re-introduce a
    # guessed normalization without this test failing first.
    field_names = {f.name for f in dataclasses.fields(EvidenceRecord)}
    assert "h_comp_normalized" not in field_names
    assert "normalized_h_comp" not in field_names


def test_measured_and_derived_are_distinct_types():
    assert MeasuredValue is not DerivedValue
    assert not issubclass(MeasuredValue, DerivedValue)
    assert not issubclass(DerivedValue, MeasuredValue)
    assert MeasuredValue(1.0) != DerivedValue(1.0)


def test_eou_spec_identity_fields():
    identity = EOUSpecIdentity(seed_set_id="EOU-128-v1", eou_spec_version="2.0.0")
    assert identity.seed_set_id == "EOU-128-v1"
    assert identity.eou_spec_version == "2.0.0"


def test_evidence_record_composes_from_pure_function_outputs():
    # Synthetic covariance matrix and grounded_state -- arithmetic inputs,
    # not a claim of a real observation. observation_state is honestly
    # NOT_EVALUABLE because no real Port evaluation has occurred.
    synthetic_covariance = np.diag([1.0, 2.0, 3.0])
    var_s = canonical_variance(synthetic_covariance)
    h_comp = raw_spectral_entropy(np.diag(synthetic_covariance))
    state_hash = canonical_tag_hash({"synthetic_test_field": "placeholder"})

    record = EvidenceRecord(
        port_id="P01",
        eou_spec_identity=EOUSpecIdentity(seed_set_id="EOU-128-v1", eou_spec_version="2.0.0"),
        state_hash=state_hash,
        var_s=DerivedValue(var_s),
        h_comp_raw=DerivedValue(h_comp),
        observation_state=ObservationState.NOT_EVALUABLE,
        attestation_ref="synthetic-test-placeholder",
    )

    assert record.var_s.value == pytest.approx(6.0)
    assert record.observation_state is ObservationState.NOT_EVALUABLE
    assert len(record.state_hash) == 64


def test_evidence_record_is_immutable():
    record = EvidenceRecord(
        port_id="P01",
        eou_spec_identity=EOUSpecIdentity(seed_set_id="EOU-128-v1", eou_spec_version="2.0.0"),
        state_hash="0" * 64,
        var_s=DerivedValue(1.0),
        h_comp_raw=DerivedValue(0.5),
        observation_state=ObservationState.NOT_EVALUABLE,
        attestation_ref="placeholder",
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        record.port_id = "P02"  # type: ignore[misc]


def test_empty_port_id_rejected():
    with pytest.raises(ValueError, match="port_id"):
        EvidenceRecord(
            port_id="",
            eou_spec_identity=EOUSpecIdentity(seed_set_id="EOU-128-v1", eou_spec_version="2.0.0"),
            state_hash="0" * 64,
            var_s=DerivedValue(1.0),
            h_comp_raw=DerivedValue(0.5),
            observation_state=ObservationState.NOT_EVALUABLE,
            attestation_ref="placeholder",
        )


def test_malformed_state_hash_rejected():
    with pytest.raises(ValueError, match="state_hash"):
        EvidenceRecord(
            port_id="P01",
            eou_spec_identity=EOUSpecIdentity(seed_set_id="EOU-128-v1", eou_spec_version="2.0.0"),
            state_hash="not-a-valid-hash",
            var_s=DerivedValue(1.0),
            h_comp_raw=DerivedValue(0.5),
            observation_state=ObservationState.NOT_EVALUABLE,
            attestation_ref="placeholder",
        )
