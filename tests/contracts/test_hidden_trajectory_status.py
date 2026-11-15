"""HiddenTrajectoryResult.status: PASS / PASS_UNVERIFIED / FAIL from violations and unverifiable (no layers)."""

from __future__ import annotations

from contracts.check import Violation
from contracts.hidden_trajectory import (
    STATUS_FAIL,
    STATUS_PASS,
    STATUS_PASS_UNVERIFIED,
    HiddenTrajectoryResult,
    Unverifiable,
    check_hidden_trajectory,
)
from contracts.hidden_trajectory_window import check_window_space
from test_hidden_trajectory import BLOBS, MLP, envelope_of, payload_of
from test_hidden_trajectory_contract import facts_of
from test_window_space import SPACE_E, SPACE_F, parent_payload, stored_of, window_of


def test_status_constants() -> None:
    assert (STATUS_PASS, STATUS_PASS_UNVERIFIED, STATUS_FAIL) == (
        "PASS",
        "PASS_UNVERIFIED",
        "FAIL",
    )


def test_status_from_the_two_lists() -> None:
    empty = HiddenTrajectoryResult()
    assert empty.status == STATUS_PASS and empty.ok
    only_u = HiddenTrajectoryResult((), (Unverifiable("x", "y"),))
    assert only_u.status == STATUS_PASS_UNVERIFIED and only_u.ok
    only_v = HiddenTrajectoryResult((Violation("c", "m"),), ())
    assert only_v.status == STATUS_FAIL and not only_v.ok
    both = HiddenTrajectoryResult((Violation("c", "m"),), (Unverifiable("x", "y"),))
    assert both.status == STATUS_FAIL and not both.ok


def test_accept_with_blobs_and_contract_facts_is_pass() -> None:
    p = payload_of(MLP)
    result = check_hidden_trajectory(
        envelope_of(p), None, BLOBS, contract_facts=facts_of(p)
    )
    assert result.violations == () and result.unverifiable == ()
    assert result.status == STATUS_PASS


def test_accept_without_blobs_or_facts_is_pass_unverified() -> None:
    result = check_hidden_trajectory(envelope_of(payload_of(MLP)), None, None)
    assert result.ok and result.status == STATUS_PASS_UNVERIFIED
    assert {u.check for u in result.unverifiable} >= {
        "token_index_bytes",
        "points_bytes",
        "contract_binding",
    }


def test_a_broken_field_is_fail() -> None:
    result = check_hidden_trajectory(
        envelope_of(payload_of(MLP, dimension=7)), None, BLOBS
    )
    assert result.violations and result.status == STATUS_FAIL


def test_window_space_uses_the_same_status_rule() -> None:
    parent = parent_payload()
    for start, space in ((0, SPACE_E), (128, SPACE_F)):
        result = check_window_space(
            window_of(parent, start, space_id=space), stored_of(parent)
        )
        assert result.status == STATUS_PASS
    foreign = {
        next(iter(stored_of(parent))): {
            "envelope": {
                "payload_schema": {
                    "id": "msr.trajectory-window",
                    "version": "0.10.0",
                },
                "payload": {},
            }
        }
    }
    unverifiable = check_window_space(window_of(parent), foreign)
    assert unverifiable.status == STATUS_PASS_UNVERIFIED and unverifiable.ok
    wrong = check_window_space(
        window_of(parent, space_id="hid:" + "0" * 64), stored_of(parent)
    )
    assert wrong.status == STATUS_FAIL and not wrong.ok
