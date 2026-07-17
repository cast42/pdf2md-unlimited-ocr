"""Convert PDFs to Markdown with temporary page images."""

from __future__ import annotations

import shutil
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .markdown import render_grounded_markdown
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
    asset_directory: Path | None = None


def markdown_path_for(pdf_path: Path) -> Path:
    """Return the default Markdown path for a PDF path."""
    return pdf_path.with_suffix(".md")


def asset_path_for(pdf_path: Path) -> Path:
    """Return the default extracted visual asset directory for a PDF."""
    return pdf_path.with_name(f"{pdf_path.stem}_assets")


def convert_pdf(
    pdf_path: Path,
    ocr: OcrBackend,
    *,
    dpi: int = 300,
    keep_images: bool = False,
    asset_directory: Path | None = None,
    progress: Callable[[int, int], None] | None = None,
) -> ConversionResult:
    """Render a PDF, run OCR, preserve its layout, and remove page images."""
    image_directory = Path(tempfile.mkdtemp(prefix=f"pdf2md-{pdf_path.stem}-"))
    try:
        image_paths = render_pdf(pdf_path, image_directory, dpi=dpi)
        temporary_assets = image_directory / "assets" if asset_directory is not None else None
        document = render_grounded_markdown(
            ocr.parse(image_paths, progress=progress),
            image_paths,
            asset_directory=temporary_assets,
            asset_reference=Path(asset_directory.name) if asset_directory is not None else None,
        )
        published_assets = None
        if asset_directory is not None and document.asset_count:
            if asset_directory.exists():
                shutil.rmtree(asset_directory)
            shutil.move(str(temporary_assets), asset_directory)
            published_assets = asset_directory
        return ConversionResult(
            markdown=document.text,
            image_directory=image_directory if keep_images else None,
            asset_directory=published_assets,
        )
    except Exception as error:
        if keep_images:
            raise ConversionError(str(error), image_directory) from error
        raise
    finally:
        if not keep_images:
            shutil.rmtree(image_directory, ignore_errors=True)
