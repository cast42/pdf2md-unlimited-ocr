"""Run Unlimited OCR through MLX-VLM on Apple Silicon."""

from __future__ import annotations

from pathlib import Path
from typing import Any

DEFAULT_MODEL = "baidu/Unlimited-OCR"


class OcrError(RuntimeError):
    """Raised when the OCR model cannot load or generate text."""


class UnlimitedOcr:
    """A loaded Unlimited OCR model and processor."""

    def __init__(self, model: Any, processor: Any) -> None:
        """Store a loaded MLX model and processor."""
        self.model = model
        self.processor = processor

    @classmethod
    def load(cls, model_id: str = DEFAULT_MODEL) -> UnlimitedOcr:
        """Load the requested model with MLX-VLM."""
        try:
            from mlx_vlm import load

            model, processor = load(model_id)
        except Exception as error:
            raise OcrError(f"Could not load model {model_id}: {error}") from error
        return cls(model, processor)

    def parse(self, image_paths: list[Path]) -> str:
        """Parse ordered PDF page images and return the model text."""
        if not image_paths:
            raise OcrError("No page images were provided to the OCR model")

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
                verbose=False,
            )
        except Exception as error:
            raise OcrError(f"OCR failed: {error}") from error

        if not result.text.strip():
            raise OcrError("OCR returned no text")
        return result.text
