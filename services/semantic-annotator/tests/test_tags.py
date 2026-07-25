from app.tags import extract_json_object, parse_tags


def test_extract_json_object_strips_surrounding_prose():
    raw = 'Sure, here it is:\n```json\n{"tags": {"T10_epistemic_confidence": 0.7}}\n```'
    data = extract_json_object(raw)
    assert data == {"tags": {"T10_epistemic_confidence": 0.7}}


def test_extract_json_object_raises_on_no_json():
    try:
        extract_json_object("no json here")
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_parse_tags_defaults_when_missing():
    parsed = parse_tags({})
    assert parsed["T09_strategic_interest_vector"] == {
        "security": 0.0, "economy": 0.0, "technology": 0.0,
        "resources": 0.0, "ideology": 0.0, "environment": 0.0,
    }
    assert parsed["T10_epistemic_confidence"] == 0.5
    assert parsed["T19_conflict_factuality_index"] == 0.0
    assert parsed["T03_predicate_type"] is None
    assert parsed["T07_actor_role"] is None
    assert parsed["T08_causality_direction"] is None
    assert parsed["T11_bias_component"] is None
    assert parsed["T16_economic_transmission_path"] is None


def test_parse_tags_clamps_out_of_range_values():
    data = {
        "tags": {
            "T09_strategic_interest_vector": {"security": 5.0, "economy": -5.0},
            "T10_epistemic_confidence": 1.5,
            "T19_conflict_factuality_index": -0.5,
        }
    }
    parsed = parse_tags(data)
    assert parsed["T09_strategic_interest_vector"]["security"] == 1.0
    assert parsed["T09_strategic_interest_vector"]["economy"] == -1.0
    assert parsed["T10_epistemic_confidence"] == 1.0
    assert parsed["T19_conflict_factuality_index"] == 0.0


def test_parse_tags_actor_role_rejects_out_of_vocabulary():
    data = {
        "tags": {
            "T07_actor_role": {
                "actor_type": "not-a-real-type",
                "actor_scale": "state",
                "actor_perspective": "self",
            }
        }
    }
    parsed = parse_tags(data)
    assert parsed["T07_actor_role"] is None


def test_parse_tags_actor_role_accepts_closed_vocab():
    data = {
        "tags": {
            "T07_actor_role": {
                "actor_type": "state",
                "actor_scale": "state",
                "actor_perspective": "self",
            }
        }
    }
    parsed = parse_tags(data)
    assert parsed["T07_actor_role"] == {
        "actor_type": "state", "actor_scale": "state", "actor_perspective": "self",
    }


def test_parse_tags_bias_component_requires_two_element_gravity():
    data = {"tags": {"T11_bias_component": {"emotional_load": 0.5, "sentiment_gravity": [0.1]}}}
    assert parse_tags(data)["T11_bias_component"] is None

    data_ok = {"tags": {"T11_bias_component": {"emotional_load": 0.5, "sentiment_gravity": [0.1, -0.2]}}}
    parsed = parse_tags(data_ok)
    assert parsed["T11_bias_component"] == {"emotional_load": 0.5, "sentiment_gravity": [0.1, -0.2]}


def test_parse_tags_economic_transmission_path_filters_non_strings():
    data = {"tags": {"T16_economic_transmission_path": ["energy", "", 42, "finance"]}}
    assert parse_tags(data)["T16_economic_transmission_path"] == ["energy", "finance"]
