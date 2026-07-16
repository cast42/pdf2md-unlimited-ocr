"""Tests for PDF rendering and conversion."""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from pathlib import Path

import pytest
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen.canvas import Canvas

from pdf2md_unlimited_ocr.converter import convert_pdf
from pdf2md_unlimited_ocr.markdown import clean_markdown
from pdf2md_unlimited_ocr.ocr import UnlimitedOcr

SOURCE_MARKDOWN = """# Simple OCR Test

The quick brown fox jumps over the lazy dog.

The answer is 42.
"""


def markdown_to_pdf(markdown: str, pdf_path: Path) -> None:
    """Render the small Markdown subset used by the roundtrip fixture."""
    canvas = Canvas(str(pdf_path), pagesize=A4)
    _, page_height = A4
    y = page_height - 72

    for line in markdown.splitlines():
        if not line:
            y -= 14
            continue
        if line.startswith("# "):
            canvas.setFont("Helvetica-Bold", 20)
            canvas.drawString(72, y, line.removeprefix("# "))
            y -= 32
        else:
            canvas.setFont("Helvetica", 12)
            canvas.drawString(72, y, line)
            y -= 20

    canvas.save()


def comparable_text(markdown: str) -> str:
    """Normalize Markdown decoration and whitespace for OCR comparison."""
    without_markup = re.sub(r"[^\w\s]", " ", markdown.casefold())
    return " ".join(without_markup.split())


class EchoOcr:
    """Small OCR substitute for testing the conversion pipeline."""

    def __init__(self) -> None:
        """Create an empty list of observed image paths."""
        self.image_paths: list[Path] = []

    def parse(self, image_paths: list[Path]) -> str:
        """Record rendered paths and return fixed model output."""
        self.image_paths = image_paths
        assert all(path.exists() for path in image_paths)
        return "<|det|>title [0, 0, 100, 100]<|/det|># Test\n<PAGE>\nDone"


def test_convert_pdf_renders_and_removes_page_images(tmp_path: Path) -> None:
    """The pipeline should render with PDFium and clean temporary images."""
    pdf_path = tmp_path / "sample.pdf"
    markdown_to_pdf(SOURCE_MARKDOWN, pdf_path)
    ocr = EchoOcr()

    result = convert_pdf(pdf_path, ocr, dpi=144)

    assert result.markdown == "# Test\n\n<!-- Page break -->\n\nDone\n"
    assert [path.name for path in ocr.image_paths] == ["page_0001.png"]
    assert not ocr.image_paths[0].exists()


def test_clean_markdown_removes_model_tokens() -> None:
    """Model markers should not appear in final Markdown."""
    model_text = (
        "<｜begin▁of▁sentence｜><|det|>text [1, 2, 3, 4]<|/det|>Hello"
        "<PAGE>World<｜end▁of▁sentence｜>"
    )

    assert clean_markdown(model_text) == "Hello\n\n<!-- Page break -->\n\nWorld\n"


@pytest.mark.integration
def test_pdf_markdown_roundtrip_with_unlimited_ocr(tmp_path: Path) -> None:
    """A simple Markdown page should survive PDF rendering and real OCR."""
    pdf_path = tmp_path / "roundtrip.pdf"
    markdown_to_pdf(SOURCE_MARKDOWN, pdf_path)

    ocr = UnlimitedOcr.load()
    result = convert_pdf(pdf_path, ocr)

    expected = comparable_text(SOURCE_MARKDOWN)
    actual = comparable_text(result.markdown)
    similarity = SequenceMatcher(None, expected, actual).ratio()

    assert similarity >= 0.80, (
        f"Markdown roundtrip similarity was {similarity:.1%}\n"
        f"Expected:\n{SOURCE_MARKDOWN}\n"
        f"Generated:\n{result.markdown}"
    )
