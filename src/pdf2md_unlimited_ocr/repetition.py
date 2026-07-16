"""MLX repetition guard matching Baidu's Unlimited OCR examples."""

from __future__ import annotations

import importlib
from typing import Any


def banned_next_tokens(sequence: list[int], ngram_size: int, window: int) -> set[int]:
    """Return tokens that would repeat an n-gram in the recent window."""
    if ngram_size <= 0 or window <= 0 or len(sequence) < ngram_size:
        return set()

    search_start = max(0, len(sequence) - window)
    search_end = len(sequence) - ngram_size + 1
    if search_end <= search_start:
        return set()

    current_prefix = tuple(sequence[-(ngram_size - 1) :]) if ngram_size > 1 else ()
    banned: set[int] = set()
    for index in range(search_start, search_end):
        ngram = sequence[index : index + ngram_size]
        if ngram_size == 1 or tuple(ngram[:-1]) == current_prefix:
            banned.add(ngram[-1])
    return banned


class SlidingWindowNoRepeatNgramProcessor:
    """Block repeated n-grams within a fixed window during MLX generation."""

    def __init__(self, ngram_size: int, window: int) -> None:
        """Store the n-gram size and search window."""
        self.ngram_size = ngram_size
        self.window = window

    def __call__(self, tokens: Any, logits: Any) -> Any:
        """Set logits for banned next tokens to negative infinity."""
        banned = banned_next_tokens(tokens.tolist(), self.ngram_size, self.window)
        if not banned:
            return logits

        mx: Any = importlib.import_module("mlx.core")
        indices = mx.array(sorted(banned), dtype=mx.int32)
        return logits.at[:, indices].add(float("-inf"))
