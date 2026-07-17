"""Turn grounded Unlimited OCR output into readable Markdown."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

_CONTROL_TOKENS = (
    "<｜begin▁of▁sentence｜>",
    "<｜end▁of▁sentence｜>",
    "<｜▁pad▁｜>",
    "<s>",
    "</s>",
)
_DETECTION = re.compile(r"<\|det\|>.*?<\|/det\|>", flags=re.DOTALL)
_PAGE = re.compile(r"\s*<PAGE>\s*")
_GROUNDING = re.compile(
    r"<\|det\|>(?P<label>[^[]+?)\s*\[(?P<box>[^]]+)]<\|/det\|>",
    flags=re.DOTALL,
)
_VISUAL_LABELS = {"chart", "figure", "image", "map"}
_COMPLEX_TABLE_AREA = 60_000
_RUNNING_LABELS = {"footer", "header", "page_footer", "page_header"}
_HEADING_LEVELS = {"section_header": 3, "title": 2}
_COLUMN_HEADER_WORDS = {"timing", "wat", "what", "when", "who", "wie"}
ImageDescriptionCallback = Callable[[Path, str], str]


@dataclass(frozen=True)
class GroundedBlock:
    """One model layout block with normalized coordinates and content."""

    label: str
    box: tuple[int, int, int, int]
    content: str


@dataclass(frozen=True)
class MarkdownDocument:
    """Rendered Markdown and the number of extracted visual assets."""

    text: str
    asset_count: int = 0


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


def contains_describable_visuals(text: str) -> bool:
    """Return whether grounded output contains a visual that will be extracted."""
    pages = _PAGE.split(_remove_control_tokens(strip_ungrounded_preamble(text)))
    for page in pages:
        blocks = _grounded_blocks(page)
        if _fragmented_table(blocks) is not None:
            return True
        for block in blocks:
            label = _normalized_label(block.label)
            if label in _VISUAL_LABELS:
                return True
            if label == "table" and _box_area(block.box) >= _COMPLEX_TABLE_AREA:
                return True
    return False


def render_grounded_markdown(
    text: str,
    image_paths: list[Path],
    *,
    asset_directory: Path | None = None,
    asset_reference: Path | None = None,
    describe_image: ImageDescriptionCallback | None = None,
) -> MarkdownDocument:
    """Preserve grounded layout and optionally crop detected visual regions."""
    pages = _PAGE.split(_remove_control_tokens(strip_ungrounded_preamble(text)))
    rendered_pages: list[str] = []
    asset_count = 0

    for page_index, page in enumerate(pages):
        blocks = _grounded_blocks(page)
        fragmented_table = _fragmented_table(blocks)
        page_parts: list[str] = []
        visual_number = 0
        for block_index, block in enumerate(blocks):
            label = _normalized_label(block.label)
            content = block.content.strip()
            if label == "page_number" or (page_index > 0 and label in _RUNNING_LABELS):
                continue
            if (
                fragmented_table is not None
                and block_index == fragmented_table[0]
                and asset_directory is not None
                and page_index < len(image_paths)
            ):
                visual_number += 1
                asset_name = f"page_{page_index + 1:04d}_table_{visual_number:02d}.png"
                if _crop_visual(image_paths[page_index], fragmented_table[1], asset_directory / asset_name):
                    reference = (asset_reference or asset_directory) / asset_name
                    page_parts.append(
                        _visual_markdown(
                            reference,
                            f"Table on page {page_index + 1}",
                            asset_directory / asset_name,
                            "complex table",
                            describe_image,
                        )
                    )
                    asset_count += 1
            if label in _VISUAL_LABELS:
                visual_number += 1
                caption = _following_caption(blocks, block_index)
                if asset_directory is not None and page_index < len(image_paths):
                    asset_name = f"page_{page_index + 1:04d}_{label}_{visual_number:02d}.png"
                    if _crop_visual(image_paths[page_index], block.box, asset_directory / asset_name):
                        reference = (asset_reference or asset_directory) / asset_name
                        page_parts.append(
                            _visual_markdown(
                                reference,
                                caption or label.title(),
                                asset_directory / asset_name,
                                f"{label}: {caption}" if caption else label,
                                describe_image,
                            )
                        )
                        asset_count += 1
                continue
            if label == "table":
                if (
                    asset_directory is not None
                    and page_index < len(image_paths)
                    and fragmented_table is None
                    and _box_area(block.box) >= _COMPLEX_TABLE_AREA
                ):
                    visual_number += 1
                    asset_name = f"page_{page_index + 1:04d}_table_{visual_number:02d}.png"
                    if _crop_visual(image_paths[page_index], block.box, asset_directory / asset_name):
                        reference = (asset_reference or asset_directory) / asset_name
                        page_parts.append(
                            _visual_markdown(
                                reference,
                                f"Table on page {page_index + 1}",
                                asset_directory / asset_name,
                                "complex table",
                                describe_image,
                            )
                        )
                        asset_count += 1
                if content:
                    page_parts.append(content)
                continue
            if label == "image_caption":
                if content:
                    page_parts.append(f"*{content}*")
                continue
            if label in _HEADING_LEVELS and content:
                page_parts.append(_heading(content, _HEADING_LEVELS[label], page_index))
                continue
            if content:
                page_parts.append(content)

        rendered = "\n\n".join(part.strip() for part in page_parts if part.strip())
        rendered_pages.append(rendered)

    markdown = "\n\n<!-- Page break -->\n\n".join(rendered_pages)
    markdown = "\n".join(line.rstrip() for line in markdown.splitlines()).strip()
    return MarkdownDocument(f"{markdown}\n" if markdown else "", asset_count)


def _remove_control_tokens(text: str) -> str:
    """Remove model tokens without discarding grounded layout markers."""
    for token in _CONTROL_TOKENS:
        text = text.replace(token, "")
    return text


def _grounded_blocks(page: str) -> list[GroundedBlock]:
    """Parse a page into layout blocks in the model's reading order."""
    matches = list(_GROUNDING.finditer(page))
    blocks: list[GroundedBlock] = []
    seen_boxes: set[tuple[int, int, int, int]] = set()
    for index, match in enumerate(matches):
        content_end = matches[index + 1].start() if index + 1 < len(matches) else len(page)
        coordinates = [int(value) for value in re.findall(r"-?\d+", match.group("box"))]
        if len(coordinates) != 4:
            continue
        box = (coordinates[0], coordinates[1], coordinates[2], coordinates[3])
        if box in seen_boxes:
            continue
        seen_boxes.add(box)
        blocks.append(
            GroundedBlock(
                label=match.group("label").strip(),
                box=box,
                content=page[match.end() : content_end],
            )
        )
    if not blocks and page.strip():
        blocks.append(GroundedBlock("text", (0, 0, 1000, 1000), page))
    return blocks


def _normalized_label(label: str) -> str:
    """Normalize model label spelling for layout decisions."""
    return re.sub(r"[^a-z0-9]+", "_", label.casefold()).strip("_")


def _following_caption(blocks: list[GroundedBlock], index: int) -> str:
    """Return an immediately following image caption, when present."""
    if index + 1 >= len(blocks):
        return ""
    following = blocks[index + 1]
    if _normalized_label(following.label) != "image_caption":
        return ""
    return following.content.strip()


def _box_area(box: tuple[int, int, int, int]) -> int:
    """Return the area of a normalized model bounding box."""
    left, top, right, bottom = box
    return max(0, right - left) * max(0, bottom - top)


def _fragmented_table(blocks: list[GroundedBlock]) -> tuple[int, tuple[int, int, int, int]] | None:
    """Find a table split into aligned column headers and separate blocks."""
    headers = [
        (index, block)
        for index, block in enumerate(blocks)
        if re.sub(r"[^a-z]+", "", block.content.casefold().strip()) in _COLUMN_HEADER_WORDS
    ]
    for header_index, (_, first_header) in enumerate(headers):
        aligned = [item for item in headers[header_index:] if abs(item[1].box[1] - first_header.box[1]) <= 40]
        if len(aligned) < 2:
            continue
        first_index = min(index for index, _ in aligned)
        top = min(block.box[1] for _, block in aligned)
        following = [
            block
            for block in blocks[first_index:]
            if block.box[1] >= top
            and _normalized_label(block.label) != "page_number"
            and _normalized_label(block.label) not in _RUNNING_LABELS
        ]
        if not any(_normalized_label(block.label) == "table" for block in following):
            continue
        return (
            first_index,
            (
                min(block.box[0] for block in following) - 15,
                top - 5,
                max(block.box[2] for block in following) + 35,
                max(block.box[3] for block in following) + 10,
            ),
        )
    return None


def _heading(content: str, level: int, page_index: int) -> str:
    """Promote detected titles while preserving existing Markdown headings."""
    if content.lstrip().startswith("#"):
        return content
    if page_index == 0 and level == 2:
        level = 1
    return f"{'#' * level} {content}"


def _crop_visual(source: Path, box: tuple[int, int, int, int], destination: Path) -> bool:
    """Crop a normalized 0-1000 model box from a rendered page image."""
    with Image.open(source) as page_image:
        left, top, right, bottom = box
        left = max(0, min(1000, left))
        top = max(0, min(1000, top))
        right = max(0, min(1000, right))
        bottom = max(0, min(1000, bottom))
        if right <= left or bottom <= top:
            return False
        pixel_box = (
            round(left * page_image.width / 1000),
            round(top * page_image.height / 1000),
            round(right * page_image.width / 1000),
            round(bottom * page_image.height / 1000),
        )
        destination.parent.mkdir(parents=True, exist_ok=True)
        page_image.crop(pixel_box).save(destination, format="PNG", optimize=True)
    return True


def _image_markdown(reference: Path, alt_text: str) -> str:
    """Build a Markdown image with safe alt text and paths containing spaces."""
    alt_text = re.sub(r"\s+", " ", alt_text).replace("[", "\\[").replace("]", "\\]").strip()
    path = reference.as_posix()
    target = f"<{path}>" if " " in path else path
    return f"![{alt_text}]({target})"


def _visual_markdown(
    reference: Path,
    alt_text: str,
    image_path: Path,
    context: str,
    describe_image: ImageDescriptionCallback | None,
) -> str:
    """Build an image link and its optional multimodal description."""
    parts = [_image_markdown(reference, alt_text)]
    if describe_image is not None:
        description = describe_image(image_path, context).strip()
        if description:
            parts.append(f"**Image understanding:** {description}")
    return "\n\n".join(parts)
