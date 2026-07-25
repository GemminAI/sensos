import pytest

from runtime.services.redis_service import RedisService


def test_sequence_and_dedup(fake_redis):
    service = RedisService()
    from uuid import uuid4

    sid, aid = uuid4(), uuid4()
    s1 = service.next_sequence(sid, aid)
    s2 = service.next_sequence(sid, aid)
    assert s2 == s1 + 1

    eid = uuid4()
    assert service.is_duplicate(eid) is False
    assert service.is_duplicate(eid) is True
