"""Provider interface for Semantic Annotator LLM backends."""

from __future__ import annotations

from abc import ABC, abstractmethod


class BaseAnnotatorProvider(ABC):
    """One LLM backend that can turn text into a raw annotation JSON string.

    Providers only make the HTTP call and return the model's raw text
    response - parsing/validation happens in app/*.py, never here.
    """

    name: str

    @abstractmethod
    def annotate_raw(self, text: str) -> str:
        """Return the raw (unparsed) text response from the LLM."""
        ...

    @property
    @abstractmethod
    def model_name(self) -> str:
        ...
