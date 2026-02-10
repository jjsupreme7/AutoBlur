"""Base classes and data models for document parsers."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List


@dataclass
class TextRegion:
    """A piece of extractable text with its location in the document."""
    text: str
    location: dict = field(default_factory=dict)
    source_file: str = ""


@dataclass
class RedactionTarget:
    """A region that should be redacted."""
    region: TextRegion
    reason: str = ""
    replacement: str = "****"


class BaseParser(ABC):
    def __init__(self, file_path: str):
        self.file_path = file_path

    @abstractmethod
    def extract(self) -> List[TextRegion]:
        """Extract all text regions with their locations from the document."""
        pass

    @abstractmethod
    def redact(self, targets: List[RedactionTarget], output_path: str) -> None:
        """Apply redactions and write the output file."""
        pass
