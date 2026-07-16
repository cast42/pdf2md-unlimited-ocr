"""Helpers for cleaning Markdown returned by Unlimited OCR."""

from __future__ import annotations

import re

_CONTROL_TOKENS = (
    "<｜begin▁of▁sentence｜>",
    "<｜end▁of▁sentence｜>",
    "<｜▁pad▁｜>",
    "<s>",
    "</s>",
)
_DETECTION = re.compile(r"<\|det\|>.*?<\|/det\|>", flags=re.DOTALL)
_PAGE = re.compile(r"\s*<PAGE>\s*")


def strip_ungrounded_preamble(text: str) -> str:
    """Remove text emitted before the first grounded layout marker."""
    marker_position = text.find("<|det|>")
    if marker_position <= 0:
        return text
    return text[marker_position:]


def clean_markdown(text: str) -> str:
    """Remove model control markers and return normalized Markdown."""
    cleaned = strip_ungrounded_preamble(text)
    for token in _CONTROL_TOKENS:
        cleaned = cleaned.replace(token, "")
    cleaned = _DETECTION.sub("", cleaned)
    cleaned = _PAGE.sub("\n\n<!-- Page break -->\n\n", cleaned)
    cleaned = "\n".join(line.rstrip() for line in cleaned.splitlines()).strip()
    return f"{cleaned}\n" if cleaned else ""
