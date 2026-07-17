"""Convert PDFs to Markdown with temporary page images."""

from __future__ import annotations

import shutil
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .markdown import clean_markdown
from .renderer import render_pdf


class OcrBackend(Protocol):
    """Interface used by the PDF conversion pipeline."""

    def parse(
        self,
        image_paths: list[Path],
        *,
        progress: Callable[[int, int], None] | None = None,
    ) -> str:
        """Return text for ordered page images."""
        ...


class ConversionError(RuntimeError):
    """A conversion failure with a retained page image directory."""

    def __init__(self, message: str, image_directory: Path) -> None:
        """Store the failure message and retained image directory."""
        super().__init__(message)
        self.image_directory = image_directory


@dataclass(frozen=True)
class ConversionResult:
    """Markdown and optional retained image directory for one PDF."""

    markdown: str
    image_directory: Path | None = None


def markdown_path_for(pdf_path: Path) -> Path:
    """Return the default Markdown path for a PDF path."""
    return pdf_path.with_suffix(".md")


def convert_pdf(
    pdf_path: Path,
    ocr: OcrBackend,
    *,
    dpi: int = 300,
    keep_images: bool = False,
    progress: Callable[[int, int], None] | None = None,
) -> ConversionResult:
    """Render a PDF, run OCR, clean the Markdown, and remove page images."""
    image_directory = Path(tempfile.mkdtemp(prefix=f"pdf2md-{pdf_path.stem}-"))
    try:
        image_paths = render_pdf(pdf_path, image_directory, dpi=dpi)
        markdown = clean_markdown(ocr.parse(image_paths, progress=progress))
        return ConversionResult(
            markdown=markdown,
            image_directory=image_directory if keep_images else None,
        )
    except Exception as error:
        if keep_images:
            raise ConversionError(str(error), image_directory) from error
        raise
    finally:
        if not keep_images:
            shutil.rmtree(image_directory, ignore_errors=True)
