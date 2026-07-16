"""Tests for PDF rendering and conversion."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen.canvas import Canvas

from pdf2md_unlimited_ocr.converter import convert_pdf
from pdf2md_unlimited_ocr.markdown import clean_markdown, strip_ungrounded_preamble
from pdf2md_unlimited_ocr.ocr import OcrError, UnlimitedOcr, validate_model_output
from pdf2md_unlimited_ocr.repetition import banned_next_tokens

SOURCE_MARKDOWN = """# Simple OCR Test

The quick brown fox jumps over the lazy dog.

The answer is 42.
"""
PROJECT_ROOT = Path(__file__).resolve().parents[1]
REGRESSION_PDF = PROJECT_ROOT / "data" / "14159.pdf"


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
    model_text = "<｜begin▁of▁sentence｜><|det|>text [1, 2, 3, 4]<|/det|>Hello<PAGE>World<｜end▁of▁sentence｜>"

    assert clean_markdown(model_text) == "Hello\n\n<!-- Page break -->\n\nWorld\n"


@pytest.mark.parametrize("prefix", ["3.2.1\n", "1. 2. 3. 4. 5.\n", "2018-2019\n", "2017年1月1日\n"])
def test_ungrounded_model_preamble_is_removed(prefix: str) -> None:
    """Text before the first layout marker should be removed."""
    model_text = f"{prefix}<|det|>title [1, 2, 3, 4]<|/det|>Report"

    assert strip_ungrounded_preamble(model_text).startswith("<|det|>")
    assert clean_markdown(model_text) == "Report\n"


def test_normal_text_before_layout_marker_is_removed() -> None:
    """Only grounded document content should remain in parsed output."""
    model_text = "Appendix 2024\n<|det|>title [1, 2, 3, 4]<|/det|>Report"

    assert strip_ungrounded_preamble(model_text).startswith("<|det|>")
    assert clean_markdown(model_text) == "Report\n"


def test_repetition_guard_finds_a_repeated_next_token() -> None:
    """The guard should block a token that would repeat a recent n-gram."""
    assert banned_next_tokens([1, 2, 3, 1, 2], ngram_size=3, window=10) == {3}


@pytest.mark.parametrize(
    ("text", "finish_reason", "message"),
    [
        ("valid text", "length", "output token limit"),
        ("<td></td>" * 50, "stop", "repeated empty table-cell"),
    ],
)
def test_invalid_model_output_is_rejected(text: str, finish_reason: str, message: str) -> None:
    """Truncated and structurally repetitive output should fail."""
    with pytest.raises(OcrError, match=message):
        validate_model_output(text, finish_reason)


class RecordingUnlimitedOcr(UnlimitedOcr):
    """Unlimited OCR substitute that records page batches."""

    def __init__(self, pages_per_batch: int) -> None:
        """Create a substitute without loading an MLX model."""
        super().__init__(model=object(), processor=object(), pages_per_batch=pages_per_batch)
        self.batches: list[list[Path]] = []

    def _parse_batch(self, image_paths: list[Path]) -> str:
        """Record one batch and return its filenames."""
        self.batches.append(image_paths)
        return " ".join(path.name for path in image_paths)


def test_ocr_splits_long_documents_into_page_batches() -> None:
    """Long documents should use bounded page batches in source order."""
    image_paths = [Path(f"page_{number:04d}.png") for number in range(1, 11)]
    ocr = RecordingUnlimitedOcr(pages_per_batch=4)

    output = ocr.parse(image_paths)

    assert [len(batch) for batch in ocr.batches] == [4, 4, 2]
    assert [path for batch in ocr.batches for path in batch] == image_paths
    assert output.count("<PAGE>") == 2


@pytest.mark.integration
def test_vlaanderen_pdf_converts_without_repeated_preamble() -> None:
    """The real regression PDF should convert completely without fake numbering."""
    assert REGRESSION_PDF.is_file(), f"Missing {REGRESSION_PDF}. Run `just download-test-data` first."
    ocr = UnlimitedOcr.load()
    result = convert_pdf(REGRESSION_PDF, ocr)

    assert result.markdown.count("<!-- Page break -->") == 21
    assert len(result.markdown) >= 10_000
    assert re.match(r"^\s*1\.\s+2\.\s+3\.\s+4\.", result.markdown) is None
    assert "rapport" in result.markdown[:500].casefold()
