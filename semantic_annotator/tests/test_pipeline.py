from semantic_annotator.annotator import PassthroughAnnotator
from semantic_annotator.models import Observation
from semantic_annotator.pipeline import run_pipeline


def test_run_pipeline_annotates_every_observation(observation: Observation) -> None:
    other = Observation(
        id="obs-2",
        source=observation.source,
        timestamp=observation.timestamp,
        payload={},
    )

    results = list(run_pipeline([observation, other], PassthroughAnnotator()))

    assert [r.observation.id for r in results] == ["obs-1", "obs-2"]
