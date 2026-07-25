from __future__ import annotations

import pytest

from hekb_mcp.client import HekbRuntimeClient, HekbRuntimeError
from hekb_mcp.tests.fake_hekb_runtime import FakeHekbRuntime


def make_client(fake: FakeHekbRuntime) -> HekbRuntimeClient:
    return HekbRuntimeClient(base_url="http://test", transport=fake.transport())


def test_get_object_returns_parsed_object():
    fake = FakeHekbRuntime()
    fake.seed_object(1, label="Yahweh", curvature=0.9, potential=5.0)
    client = make_client(fake)

    obj = client.get_object(1)

    assert obj.id == 1
    assert obj.label == "Yahweh"
    assert obj.curvature == 0.9


def test_get_object_404_raises_hekb_runtime_error():
    fake = FakeHekbRuntime()
    client = make_client(fake)

    with pytest.raises(HekbRuntimeError) as exc_info:
        client.get_object(999)

    assert exc_info.value.status_code == 404


def test_query_geodesic_found_path():
    fake = FakeHekbRuntime()
    fake.seed_geodesic(source=1, target=2, found=True, total_cost=3.5, path=[1, 5, 2])
    client = make_client(fake)

    result = client.query_geodesic(1, 2)

    assert result.found is True
    assert result.total_cost == 3.5
    assert result.path == [1, 5, 2]


def test_query_geodesic_not_found_defaults_empty_path():
    fake = FakeHekbRuntime()
    client = make_client(fake)

    result = client.query_geodesic(1, 2)

    assert result.found is False
    assert result.path == []
