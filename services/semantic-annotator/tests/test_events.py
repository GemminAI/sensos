from app.events import parse_events


def test_parse_events_well_formed():
    data = {"events": [{"predicate": "declare", "participants": ["Japan", "Tokyo"], "predicate_type": "action"}]}
    assert parse_events(data) == [
        {"predicate": "declare", "participants": ["Japan", "Tokyo"], "predicate_type": "action"}
    ]


def test_parse_events_missing_key_returns_empty_list():
    assert parse_events({}) == []


def test_parse_events_drops_items_without_predicate():
    data = {"events": [{"participants": ["Japan"]}]}
    assert parse_events(data) == []


def test_parse_events_defaults_participants_to_empty_list():
    data = {"events": [{"predicate": "declare"}]}
    assert parse_events(data) == [{"predicate": "declare", "participants": []}]
