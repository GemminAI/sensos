from semantic_annotator.annotator import KeywordAnnotator, PassthroughAnnotator
from semantic_annotator.models import Observation


def test_passthrough_annotator_produces_no_annotations(observation: Observation) -> None:
    result = PassthroughAnnotator().annotate(observation)

    assert result.observation is observation
    assert result.annotations == ()


def test_keyword_annotator_matches_text(observation: Observation) -> None:
    annotator = KeywordAnnotator(keywords={"cat": "animal"})

    result = annotator.annotate(observation)

    assert [a.label for a in result.annotations] == ["animal"]


def test_keyword_annotator_ignores_unmatched_keywords(observation: Observation) -> None:
    annotator = KeywordAnnotator(keywords={"dog": "animal"})

    result = annotator.annotate(observation)

    assert result.annotations == ()
