"""Tests for RFC-NVS76 Semantic Stream ABI."""

from sensos.abi.nvs74.object import ObservationObject
from sensos.abi.nvs76.stream import SemanticStream
from sensos.abi.nvs76.trajectory import SemanticTrajectory


def _obj(step: int) -> ObservationObject:
    return ObservationObject(step=step, text=f"state-{step}", metrics={"curvature_kappa": 0.1})


def test_semantic_stream_window():
    stream = SemanticStream(stream_id="test")
    for i in range(1, 8):
        stream.append(_obj(i))
    window = stream.get_window(5)
    assert [o.step for o in window] == [3, 4, 5, 6, 7]


def test_semantic_trajectory_delegates_to_stream():
    stream = SemanticStream(stream_id="test")
    stream.append(_obj(1))
    trajectory = SemanticTrajectory(stream, window_size=3)
    assert len(trajectory.get_current_trajectory()) == 1
