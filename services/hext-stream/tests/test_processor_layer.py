"""Unit tests for HEXT STREAM v1.1 Processor Layer."""

from hext_stream.processors import (
    DiagramProcessor,
    FlowProcessor,
    KanProcessor,
    ObservationProcessor,
    Pipeline,
    ProcessorRegistry,
    TrajectoryProcessor,
)
from hext_stream.schema.base import HextObject
from hext_stream.schema.type_registry import is_processor_extension_type, is_registered_type


def test_registry_register_dispatch():
    registry = ProcessorRegistry()
    registry.register(ObservationProcessor())
    obs = HextObject(source="t", type="observation", payload={})
    outputs = registry.dispatch(obs)
    assert len(outputs) == 1
    assert outputs[0].type == "trajectory"
    assert outputs[0].metadata["processor"]["type"] == "observation"


def test_pipeline_chain():
    published: list[HextObject] = []

    def _pub(topic: str, obj: HextObject) -> str:
        published.append(obj)
        return "evt-1"

    pipeline = Pipeline(
        ObservationProcessor(),
        TrajectoryProcessor(),
        FlowProcessor(),
        publish_fn=_pub,
        topic_resolver=lambda t: t,
    )
    obs = HextObject(source="t", type="observation", payload={})
    result = pipeline.execute("Observation", obs)
    types = {e.type for e in result}
    assert "observation" in types
    assert "trajectory" in types
    assert "trajectory.flow" in types
    assert "hom" in types
    assert "diagram" in types


def test_extension_types_registered():
    assert is_registered_type("hom")
    assert is_registered_type("observation")
    assert is_processor_extension_type("kan_completion")
    assert not is_processor_extension_type("observation")


def test_kan_processor_placeholder():
    proc = KanProcessor()
    diagram = HextObject(source="t", type="diagram", payload={})
    outputs = proc.process(diagram)
    assert len(outputs) == 1
    assert outputs[0].type == "kan_completion"
    assert outputs[0].payload.get("placeholder") is True
