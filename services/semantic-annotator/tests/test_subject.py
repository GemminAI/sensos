from app.subject import parse_subject


def test_parse_subject_well_formed():
    data = {"subject": {"primary": "Tokyo", "type": "location", "description": "capital of Japan"}}
    assert parse_subject(data) == {"primary": "Tokyo", "type": "location", "description": "capital of Japan"}


def test_parse_subject_missing_key_returns_all_none():
    assert parse_subject({}) == {"primary": None, "type": None, "description": None}


def test_parse_subject_wrong_type_returns_all_none():
    assert parse_subject({"subject": "not an object"}) == {"primary": None, "type": None, "description": None}


def test_parse_subject_drops_blank_strings():
    data = {"subject": {"primary": "  ", "type": "state", "description": None}}
    parsed = parse_subject(data)
    assert parsed["primary"] is None
    assert parsed["type"] == "state"
    assert parsed["description"] is None
