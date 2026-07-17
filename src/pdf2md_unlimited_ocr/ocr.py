"""Run Unlimited OCR through MLX-VLM on Apple Silicon."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from .markdown import strip_ungrounded_preamble
from .repetition import SlidingWindowNoRepeatNgramProcessor

DEFAULT_MODEL = "baidu/Unlimited-OCR"
DEFAULT_PAGES_PER_BATCH = 1
_REPEATED_EMPTY_CELLS = "<td></td>" * 50
PageProgressCallback = Callable[[int, int], None]


class OcrError(RuntimeError):
    """Raised when the OCR model cannot load or generate text."""


def validate_model_output(text: str, finish_reason: str | None) -> str:
    """Reject empty, truncated, or structurally repetitive model output."""
    if not text.strip():
        raise OcrError("OCR returned no text")
    if finish_reason == "length":
        raise OcrError("OCR reached its output token limit before completing a page batch")

    cleaned = strip_ungrounded_preamble(text)
    compact_text = "".join(cleaned.split())
    if _REPEATED_EMPTY_CELLS in compact_text:
        raise OcrError("OCR produced a repeated empty table-cell sequence")
    return cleaned


class UnlimitedOcr:
    """A loaded Unlimited OCR model and processor."""

    def __init__(self, model: Any, processor: Any, pages_per_batch: int = DEFAULT_PAGES_PER_BATCH) -> None:
        """Store a loaded MLX model and processor."""
        if pages_per_batch <= 0:
            raise ValueError("Pages per batch must be a positive integer")
        self.model = model
        self.processor = processor
        self.pages_per_batch = pages_per_batch

    @classmethod
    def load(
        cls,
        model_id: str = DEFAULT_MODEL,
        pages_per_batch: int = DEFAULT_PAGES_PER_BATCH,
    ) -> UnlimitedOcr:
        """Load the requested model with MLX-VLM."""
        try:
            from mlx_vlm import load

            model, processor = load(model_id)
        except Exception as error:
            raise OcrError(f"Could not load model {model_id}: {error}") from error
        return cls(model, processor, pages_per_batch=pages_per_batch)

    def parse(
        self,
        image_paths: list[Path],
        *,
        progress: PageProgressCallback | None = None,
    ) -> str:
        """Parse ordered PDF page images and return the model text."""
        if not image_paths:
            raise OcrError("No page images were provided to the OCR model")

        completed = 0
        if progress is not None:
            progress(completed, len(image_paths))

        outputs = []
        for start in range(0, len(image_paths), self.pages_per_batch):
            batch = image_paths[start : start + self.pages_per_batch]
            outputs.append(self._parse_batch(batch))
            completed += len(batch)
            if progress is not None:
                progress(completed, len(image_paths))
        return "\n<PAGE>\n".join(outputs)

    def _parse_batch(self, image_paths: list[Path]) -> str:
        """Parse one bounded batch of ordered page images."""
        try:
            from mlx_vlm import generate
            from mlx_vlm.prompt_utils import apply_chat_template

            prompt = apply_chat_template(
                self.processor,
                self.model.config,
                "Multi page parsing.",
                num_images=len(image_paths),
            )
            if not isinstance(prompt, str):
                raise OcrError("MLX-VLM returned an invalid prompt")
            result = generate(
                model=self.model,
                processor=self.processor,
                image=[str(path) for path in image_paths],
                prompt=prompt,
                max_tokens=32768,
                temperature=0.0,
                cropping=False,
                image_size=1024,
                base_size=1024,
                logits_processors=[SlidingWindowNoRepeatNgramProcessor(35, 1024)],
                verbose=False,
            )
        except Exception as error:
            raise OcrError(f"OCR failed: {error}") from error

        return validate_model_output(result.text, result.finish_reason)
