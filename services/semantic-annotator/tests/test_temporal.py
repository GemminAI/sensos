from app.temporal import parse_time


def test_parse_time_well_formed():
    data = {"time": {"absolute": "2026-07-17", "relative": "last week", "tense": "past"}}
    assert parse_time(data) == {"absolute": "2026-07-17", "relative": "last week", "tense": "past"}


def test_parse_time_missing_key_returns_all_none():
    assert parse_time({}) == {"absolute": None, "relative": None, "tense": None}


def test_parse_time_rejects_invalid_tense():
    data = {"time": {"tense": "sometime"}}
    assert parse_time(data)["tense"] is None
