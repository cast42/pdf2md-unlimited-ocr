"""Tests for PDF rendering and conversion."""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PIL import Image
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen.canvas import Canvas

from pdf2md_unlimited_ocr.converter import asset_path_for, convert_pdf
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

    def parse(self, image_paths: list[Path], *, progress: object = None) -> str:
        """Record rendered paths and return fixed model output."""
        del progress
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


def test_grounded_layout_extracts_visuals_and_removes_running_headers(tmp_path: Path) -> None:
    """Detected layout should become headings, captions, and cropped images."""
    pdf_path = tmp_path / "road safety.pdf"
    markdown_to_pdf(SOURCE_MARKDOWN, pdf_path)
    asset_directory = asset_path_for(pdf_path)

    class LayoutOcr:
        """Return representative grounded model output."""

        def parse(self, image_paths: list[Path], *, progress: object = None) -> str:
            del image_paths, progress
            return (
                "<|det|>header [100, 20, 900, 50]<|/det|>Running report header\n"
                "<|det|>title [100, 80, 900, 140]<|/det|>Road safety plan\n"
                "<|det|>image [100, 200, 900, 700]<|/det|>\n"
                "<|det|>image_caption [100, 710, 900, 750]<|/det|>Cyclists on a safe street\n"
                "<|det|>text [100, 760, 200, 790]<|/det|>Wie\n"
                "<|det|>text [400, 760, 500, 790]<|/det|>Wat\n"
                "<|det|>text [800, 760, 900, 790]<|/det|>Timing\n"
                "<|det|>table [100, 800, 250, 880]<|/det|><table><tr><td>Partner</td></tr></table>\n"
                "<|det|>table [400, 800, 700, 880]<|/det|><table><tr><td>Action</td></tr></table>\n"
                "<|det|>table [800, 800, 900, 880]<|/det|><table><tr><td>2026</td></tr></table>\n"
                "<|det|>text [100, 920, 500, 940]<|/det|>Unique grounded text\n"
                "<|det|>text [100, 920, 500, 940]<|/det|>Repeated hallucination\n"
                "<|det|>page_number [900, 950, 950, 980]<|/det|>1\n"
                "<PAGE>\n"
                "<|det|>header [100, 20, 900, 50]<|/det|>Repeated running header\n"
                "<|det|>text [100, 100, 900, 150]<|/det|>Second page text"
            )

    result = convert_pdf(pdf_path, LayoutOcr(), dpi=72, asset_directory=asset_directory)

    assert result.asset_directory == asset_directory
    assert "# Road safety plan\n\n![Cyclists on a safe street]" in result.markdown
    assert "*Cyclists on a safe street*" in result.markdown
    assert "<table><tr><td>2026</td></tr></table>" in result.markdown
    assert "Unique grounded text" in result.markdown
    assert "Repeated hallucination" not in result.markdown
    assert "Running report header" in result.markdown
    assert "Repeated running header" not in result.markdown
    assert "Second page text" in result.markdown
    image_path = asset_directory / "page_0001_image_01.png"
    assert image_path.is_file()
    with Image.open(image_path) as image:
        assert image.width > 450
        assert image.height > 400
    assert (asset_directory / "page_0001_table_02.png").is_file()


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


def test_ocr_reports_completed_pages_after_each_batch() -> None:
    """Page progress should start at zero and advance by completed batches."""
    image_paths = [Path(f"page_{number:04d}.png") for number in range(1, 6)]
    ocr = RecordingUnlimitedOcr(pages_per_batch=2)
    updates: list[tuple[int, int]] = []

    ocr.parse(image_paths, progress=lambda completed, total: updates.append((completed, total)))

    assert updates == [(0, 5), (2, 5), (4, 5), (5, 5)]


def test_pdf_ocr_uses_documented_unlimited_ocr_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """PDF batches should use the settings documented by MLX-VLM."""
    import mlx_vlm
    import mlx_vlm.prompt_utils

    model = SimpleNamespace(config=object())
    processor = object()
    template = Mock(return_value="<image>Multi page parsing.")
    generate = Mock(return_value=SimpleNamespace(text="Parsed", finish_reason="stop"))
    monkeypatch.setattr(mlx_vlm.prompt_utils, "apply_chat_template", template)
    monkeypatch.setattr(mlx_vlm, "generate", generate)

    output = UnlimitedOcr(model, processor)._parse_batch([Path("page_0001.png")])

    assert output == "Parsed"
    template.assert_called_once_with(processor, model.config, "Multi page parsing.", num_images=1)
    call = generate.call_args.kwargs
    assert call["model"] is model
    assert call["processor"] is processor
    assert call["image"] == ["page_0001.png"]
    assert call["prompt"] == "<image>Multi page parsing."
    assert call["max_tokens"] == 32768
    assert call["temperature"] == 0.0
    assert call["cropping"] is False
    assert call["image_size"] == 1024
    assert call["base_size"] == 1024
    assert call["verbose"] is False
    repetition_guard = call["logits_processors"][0]
    assert repetition_guard.ngram_size == 35
    assert repetition_guard.window == 1024


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
