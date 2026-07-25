from app.entities import parse_entities


def test_parse_entities_well_formed():
    data = {"entities": [{"text": "Tokyo", "type": "location", "normalized": "Tokyo, Japan", "salience": 0.9}]}
    assert parse_entities(data) == [
        {"text": "Tokyo", "type": "location", "normalized": "Tokyo, Japan", "salience": 0.9}
    ]


def test_parse_entities_missing_key_returns_empty_list():
    assert parse_entities({}) == []


def test_parse_entities_drops_items_without_text_or_type():
    data = {"entities": [{"text": "Tokyo"}, {"type": "location"}, {"text": "", "type": "location"}]}
    assert parse_entities(data) == []


def test_parse_entities_clamps_salience():
    data = {"entities": [{"text": "Tokyo", "type": "location", "salience": 5.0}]}
    assert parse_entities(data)[0]["salience"] == 1.0


def test_parse_entities_omits_optional_fields_when_absent():
    data = {"entities": [{"text": "Tokyo", "type": "location"}]}
    entity = parse_entities(data)[0]
    assert "normalized" not in entity
    assert "salience" not in entity
