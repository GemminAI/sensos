from runtime.services.t09_visualization import (
    T09_AXIS_LABELS,
    T09_AXES,
    dominant_axis,
    dominant_axis_label,
    euclidean_distance,
    orientation_summary,
    pairwise_distances,
    t09_vector_from_dict,
)


def test_t09_vector_from_dict():
    vec = t09_vector_from_dict({"technology": 0.62, "security": 0.1})
    assert vec[T09_AXES.index("technology")] == 0.62
    assert vec[T09_AXES.index("security")] == 0.1


def test_dominant_axis():
    assert dominant_axis({"technology": 0.62, "security": 0.1}) == "technology"
    assert dominant_axis_label({"technology": 0.62}) == "Technology"
    assert dominant_axis({"security": -0.8, "economy": 0.1}) == "security"


def test_euclidean_distance():
    a = {"security": 0.0, "economy": 0.0, "technology": 0.0, "resources": 0.0, "ideology": 0.0, "environment": 0.0}
    b = {"security": 1.0, "economy": 0.0, "technology": 0.0, "resources": 0.0, "ideology": 0.0, "environment": 0.0}
    assert round(euclidean_distance(a, b), 2) == 1.0


def test_pairwise_distances():
    states = [
        {"origin": "jp", "t09": {"technology": 0.6, "security": 0.1, "economy": 0.0, "resources": 0.0, "ideology": 0.0, "environment": 0.0}},
        {"origin": "us", "t09": {"technology": 0.3, "security": 0.5, "economy": 0.0, "resources": 0.0, "ideology": 0.0, "environment": 0.0}},
    ]
    rows = pairwise_distances(states)
    assert len(rows) == 1
    assert rows[0]["pair"] == "JP ↔ US"
    assert rows[0]["distance"] > 0


def test_orientation_summary():
    states = [
        {"origin": "us", "t09": {"security": 0.7, "economy": 0.0, "technology": 0.0, "resources": 0.0, "ideology": 0.0, "environment": 0.0}},
        {"origin": "cn", "t09": {"economy": 0.8, "security": 0.0, "technology": 0.0, "resources": 0.0, "ideology": 0.0, "environment": 0.0}},
    ]
    lines = orientation_summary(states)
    assert "US emphasizes Security." in lines
    assert "CN emphasizes Economy." in lines


def test_axis_labels_include_resource():
    assert T09_AXIS_LABELS["resources"] == "Resource"
    assert len(T09_AXES) == 6
