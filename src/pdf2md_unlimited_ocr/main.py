"""Public conversion API."""

from .converter import ConversionError, ConversionResult, convert_pdf, markdown_path_for
from .ocr import DEFAULT_MODEL, DEFAULT_PAGES_PER_BATCH, UnlimitedOcr

__all__ = [
    "DEFAULT_MODEL",
    "DEFAULT_PAGES_PER_BATCH",
    "ConversionError",
    "ConversionResult",
    "UnlimitedOcr",
    "convert_pdf",
    "markdown_path_for",
]
