from common.confidence import build_confidence

_TAGS_ALL_PRESENT = {
    "T09_strategic_interest_vector": {"security": 0.0, "economy": 0.0, "technology": 0.0, "resources": 0.0, "ideology": 0.0, "environment": 0.0},
    "T10_epistemic_confidence": 0.8,
    "T19_conflict_factuality_index": 0.1,
    "T03_predicate_type": "declare",
    "T07_actor_role": {"actor_type": "state", "actor_scale": "state", "actor_perspective": "self"},
    "T08_causality_direction": "midstream",
    "T11_bias_component": {"emotional_load": 0.1, "sentiment_gravity": [0.0, 0.0]},
    "T16_economic_transmission_path": ["energy"],
}

_TAGS_ONLY_MANDATORY = {
    "T09_strategic_interest_vector": {"security": 0.0, "economy": 0.0, "technology": 0.0, "resources": 0.0, "ideology": 0.0, "environment": 0.0},
    "T10_epistemic_confidence": 0.8,
    "T19_conflict_factuality_index": 0.1,
    "T03_predicate_type": None,
    "T07_actor_role": None,
    "T08_causality_direction": None,
    "T11_bias_component": None,
    "T16_economic_transmission_path": None,
}


def test_mandatory_tags_are_always_real():
    result = build_confidence({}, tags=_TAGS_ONLY_MANDATORY, subject={"primary": None, "type": None, "description": None}, time={"absolute": None, "relative": None, "tense": None}, location={"primary": None, "type": None, "normalized": None})
    for tag_id in ("T09_strategic_interest_vector", "T10_epistemic_confidence", "T19_conflict_factuality_index"):
        assert result["tags"][tag_id]["quality"] == "REAL"


def test_omitted_optional_tags_are_placeholder_with_reason():
    result = build_confidence({}, tags=_TAGS_ONLY_MANDATORY, subject={"primary": None, "type": None, "description": None}, time={"absolute": None, "relative": None, "tense": None}, location={"primary": None, "type": None, "normalized": None})
    for tag_id in ("T03_predicate_type", "T07_actor_role", "T08_causality_direction", "T11_bias_component", "T16_economic_transmission_path"):
        entry = result["tags"][tag_id]
        assert entry["quality"] == "PLACEHOLDER"
        assert entry["value"] is None
        assert entry["reason"]


def test_present_optional_tags_are_real():
    result = build_confidence({}, tags=_TAGS_ALL_PRESENT, subject={"primary": None, "type": None, "description": None}, time={"absolute": None, "relative": None, "tense": None}, location={"primary": None, "type": None, "normalized": None})
    for tag_id in ("T03_predicate_type", "T07_actor_role", "T08_causality_direction", "T11_bias_component", "T16_economic_transmission_path"):
        assert result["tags"][tag_id]["quality"] == "REAL"


def test_subject_placeholder_carries_reason_and_null_value():
    result = build_confidence({}, tags=_TAGS_ONLY_MANDATORY, subject={"primary": None, "type": None, "description": None}, time={"absolute": None, "relative": None, "tense": None}, location={"primary": None, "type": None, "normalized": None})
    assert result["subject"]["quality"] == "PLACEHOLDER"
    assert result["subject"]["value"] is None
    assert result["subject"]["reason"]


def test_subject_real_when_any_field_present():
    result = build_confidence({}, tags=_TAGS_ONLY_MANDATORY, subject={"primary": "Tokyo", "type": None, "description": None}, time={"absolute": None, "relative": None, "tense": None}, location={"primary": None, "type": None, "normalized": None})
    assert result["subject"]["quality"] == "REAL"


def test_entities_events_real_only_when_key_present_in_raw_data():
    no_key = build_confidence({}, tags=_TAGS_ONLY_MANDATORY, subject={"primary": None, "type": None, "description": None}, time={"absolute": None, "relative": None, "tense": None}, location={"primary": None, "type": None, "normalized": None})
    assert no_key["entities"]["quality"] == "PLACEHOLDER"
    assert no_key["events"]["quality"] == "PLACEHOLDER"

    with_empty_key = build_confidence({"entities": [], "events": []}, tags=_TAGS_ONLY_MANDATORY, subject={"primary": None, "type": None, "description": None}, time={"absolute": None, "relative": None, "tense": None}, location={"primary": None, "type": None, "normalized": None})
    assert with_empty_key["entities"]["quality"] == "REAL"
    assert with_empty_key["events"]["quality"] == "REAL"


def test_overall_confidence_is_real_and_reflects_epistemic_confidence():
    result = build_confidence({}, tags=_TAGS_ONLY_MANDATORY, subject={"primary": None, "type": None, "description": None}, time={"absolute": None, "relative": None, "tense": None}, location={"primary": None, "type": None, "normalized": None})
    assert result["overall"]["quality"] == "REAL"
    assert result["overall"]["value"] == 0.8
