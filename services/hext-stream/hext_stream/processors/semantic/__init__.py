"""EXP-4010 — Semantic Overengineering Suppression and Instruction Fidelity Control.

Passive observation processors only. The Runtime is never modified — see
`hext_stream/RFC_HEXT_STREAM_PROCESSOR_EXTENSION.md` for the v1.1 Processor
Layer contract this package builds on.
"""

from hext_stream.processors.semantic.instruction_processor import InstructionProcessor
from hext_stream.processors.semantic.required_category_processor import RequiredCategoryProcessor
from hext_stream.processors.semantic.generated_category_processor import GeneratedCategoryProcessor
from hext_stream.processors.semantic.expansion_detector import ExpansionDetector
from hext_stream.processors.semantic.lcf_detector import LCFDetector
from hext_stream.processors.semantic.sed_calculator import SEDCalculator
from hext_stream.processors.semantic.oi_calculator import OICalculator
from hext_stream.processors.semantic.if_calculator import IFCalculator
from hext_stream.processors.semantic.gain_scheduler import GainScheduler
from hext_stream.processors.semantic.controller_processor import ControllerProcessor
from hext_stream.theory.context import TheoryContext

__all__ = [
    "InstructionProcessor",
    "RequiredCategoryProcessor",
    "GeneratedCategoryProcessor",
    "ExpansionDetector",
    "LCFDetector",
    "SEDCalculator",
    "OICalculator",
    "IFCalculator",
    "GainScheduler",
    "ControllerProcessor",
]


def build_pipeline_processors(theory_context: TheoryContext | None = None) -> list:
    """The full 10-stage EXP-4010 processor chain, in pipeline order.

    RFC-HEXT016 §6 Rule 1: `theory_context` (default `None`, resolving to
    `TheoryContext.default()` inside each of the five coefficient-aware
    processors below) MUST produce bit-for-bit identical processor
    behavior to the original zero-argument construction. The four
    processors with no theory dependency (`InstructionProcessor`,
    `RequiredCategoryProcessor`, `GeneratedCategoryProcessor`,
    `ExpansionDetector`) are constructed exactly as before — untouched.
    """
    return [
        InstructionProcessor(),
        RequiredCategoryProcessor(),
        GeneratedCategoryProcessor(),
        ExpansionDetector(),
        LCFDetector(theory_context),
        SEDCalculator(theory_context),
        OICalculator(theory_context),
        IFCalculator(theory_context),
        GainScheduler(theory_context),
        ControllerProcessor(theory_context),
    ]
