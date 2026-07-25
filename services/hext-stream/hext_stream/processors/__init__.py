"""HEXT STREAM v1.1 Processor Layer — extension above Transport + Persistence."""

from hext_stream.processors.base import (
    HEXTProcessor,
    PROCESSOR_METADATA_KEY,
    derive_event,
    stamp_processor_metadata,
)
from hext_stream.processors.controller import ControllerProcessor
from hext_stream.processors.diagram import DiagramProcessor
from hext_stream.processors.flow import FlowProcessor
from hext_stream.processors.kan import KanProcessor
from hext_stream.processors.observation import ObservationProcessor
from hext_stream.processors.pipeline import DEFAULT_TOPIC_MAP, Pipeline
from hext_stream.processors.registry import ProcessorRegistry
from hext_stream.processors.trajectory import TrajectoryProcessor

__all__ = [
    "HEXTProcessor",
    "PROCESSOR_METADATA_KEY",
    "ProcessorRegistry",
    "Pipeline",
    "DEFAULT_TOPIC_MAP",
    "ObservationProcessor",
    "TrajectoryProcessor",
    "FlowProcessor",
    "DiagramProcessor",
    "KanProcessor",
    "ControllerProcessor",
    "derive_event",
    "stamp_processor_metadata",
]
