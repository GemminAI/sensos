from app.location import parse_location


def test_parse_location_well_formed():
    data = {"location": {"primary": "Tokyo", "type": "city", "normalized": "Tokyo, Japan"}}
    assert parse_location(data) == {"primary": "Tokyo", "type": "city", "normalized": "Tokyo, Japan"}


def test_parse_location_missing_key_returns_all_none():
    assert parse_location({}) == {"primary": None, "type": None, "normalized": None}


def test_parse_location_never_carries_coordinate_fields():
    """Regression guard: even if a backend ignores the prompt and returns
    lat/lon, the parser must not surface them - the schema simply has no
    field for them."""
    data = {"location": {"primary": "Tokyo", "latitude": 35.68, "longitude": 139.69}}
    parsed = parse_location(data)
    assert "latitude" not in parsed
    assert "longitude" not in parsed
