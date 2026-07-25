from runtime.services.diff_service import narrative_word_diff, t09_from_tags


def test_narrative_word_diff_added():
    result = narrative_word_diff("foo bar", "foo bar baz qux")
    assert "baz" in result["added"]
    assert "qux" in result["added"]


def test_narrative_word_diff_removed():
    result = narrative_word_diff("foo bar baz qux", "foo bar")
    assert "baz" in result["removed"]
    assert "qux" in result["removed"]


def test_narrative_word_diff_changed():
    before = "The market grew rapidly"
    after = "The market shrank rapidly"
    result = narrative_word_diff(before, after)
    assert "grew → shrank" in result["changed"]


def test_narrative_word_diff_identical():
    text = "same words here"
    result = narrative_word_diff(text, text)
    assert result == {"added": [], "removed": [], "changed": []}


def test_t09_from_tags_list():
    tags = {"T09": [0.1, 0.2, 0.31, 0.0, 0.0, 0.0]}
    t09 = t09_from_tags(tags)
    assert t09["technology"] == 0.31
    assert t09["economy"] == 0.2


def test_t09_from_tags_dict():
    tags = {"T09_strategic_interest_vector": {"technology": 0.62, "security": 0.1}}
    t09 = t09_from_tags(tags)
    assert t09["technology"] == 0.62
    assert t09["security"] == 0.1
