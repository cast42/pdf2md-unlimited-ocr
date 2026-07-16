"""Render PDF pages to ordered PNG images with PDFium."""

from __future__ import annotations

from pathlib import Path

import pypdfium2 as pdfium


class PdfRenderError(RuntimeError):
    """Raised when PDFium cannot render a PDF."""


def render_pdf(pdf_path: Path, output_directory: Path, dpi: int = 300) -> list[Path]:
    """Render every PDF page to a zero-padded PNG path."""
    if dpi <= 0:
        raise ValueError("DPI must be a positive integer")

    output_directory.mkdir(parents=True, exist_ok=True)
    image_paths: list[Path] = []
    try:
        with pdfium.PdfDocument(str(pdf_path)) as document:
            if len(document) == 0:
                raise PdfRenderError(f"PDF has no pages: {pdf_path}")

            scale = dpi / 72
            for page_number in range(len(document)):
                page = document[page_number]
                bitmap = None
                try:
                    bitmap = page.render(scale=scale)
                    image_path = output_directory / f"page_{page_number + 1:04d}.png"
                    bitmap.to_pil().save(image_path, format="PNG")
                    image_paths.append(image_path)
                finally:
                    if bitmap is not None:
                        bitmap.close()
                    page.close()
    except PdfRenderError:
        raise
    except Exception as error:
        raise PdfRenderError(f"Could not render {pdf_path}: {error}") from error

    return image_paths
