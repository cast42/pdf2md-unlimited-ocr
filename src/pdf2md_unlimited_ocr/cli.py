"""Command-line entry point for PDF to Markdown conversion."""

from __future__ import annotations

import argparse
import math
import sys
import time
from collections.abc import Sequence
from importlib.metadata import version
from pathlib import Path

from rich.console import Console
from rich.progress import BarColumn, MofNCompleteColumn, Progress, TextColumn, TimeRemainingColumn
from rich.table import Table

from .converter import ConversionError, asset_path_for, convert_pdf, markdown_path_for
from .image_understanding import DEFAULT_IMAGE_MODEL, ImageDescriber, release_model_memory
from .markdown import ImageDescriptionCallback
from .ocr import DEFAULT_MODEL, DEFAULT_PAGES_PER_BATCH, UnlimitedOcr


def input_path(value: str) -> Path:
    """Expand a leading home directory marker in an input path."""
    return Path(value).expanduser()


def format_duration(seconds: float) -> str:
    """Format a duration for the conversion statistics table."""
    if seconds < 60:
        return f"{seconds:.2f} s"
    minutes, remaining = divmod(seconds, 60)
    return f"{int(minutes)}m {remaining:.1f}s"


def percentile(values: Sequence[float], quantile: float) -> float:
    """Return a linearly interpolated percentile for non-empty values."""
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def allocate_phase_overhead(total_seconds: float, timings: Sequence[float], count: int) -> list[float]:
    """Add an equal share of unmeasured phase overhead to each work item."""
    if count == 0:
        return []
    allocated = list(timings[:count])
    allocated.extend([0.0] * (count - len(allocated)))
    overhead_per_item = max(0.0, total_seconds - sum(allocated)) / count
    return [seconds + overhead_per_item for seconds in allocated]


def print_statistics(
    console: Console,
    *,
    total_seconds: float,
    markdown_seconds: float,
    image_seconds: float,
    markdown_page_timings: Sequence[float],
    image_timings: Sequence[float],
) -> None:
    """Print aggregate conversion speed statistics to the given console."""
    page_count = len(markdown_page_timings)
    image_count = len(image_timings)
    console.print(f"Conversion statistics: {page_count} pages, {image_count} described images")
    totals = Table(title="Phase totals and averages")
    totals.add_column("Phase")
    totals.add_column("Unit")
    totals.add_column("Count", justify="right")
    totals.add_column("Total", justify="right")
    totals.add_column("Average", justify="right")
    distribution = Table(title="Per-unit distribution")
    distribution.add_column("Phase")
    distribution.add_column("Unit")
    distribution.add_column("Min", justify="right")
    distribution.add_column("P25", justify="right")
    distribution.add_column("P50", justify="right")
    distribution.add_column("P75", justify="right")
    distribution.add_column("Max", justify="right")

    def add_phase(name: str, unit: str, total: float, timings: Sequence[float]) -> None:
        """Add one phase to the totals and distribution tables."""
        if not timings:
            totals.add_row(name, unit, "0", format_duration(total), "—")
            return
        totals.add_row(
            name,
            unit,
            str(len(timings)),
            format_duration(total),
            format_duration(sum(timings) / len(timings)),
        )
        distribution.add_row(
            name,
            unit,
            format_duration(min(timings)),
            format_duration(percentile(timings, 0.25)),
            format_duration(percentile(timings, 0.50)),
            format_duration(percentile(timings, 0.75)),
            format_duration(max(timings)),
        )

    totals.add_row("All processing", "job", "1", format_duration(total_seconds), "—")
    add_phase("Markdown conversion", "page", markdown_seconds, markdown_page_timings)
    add_phase("Image descriptions", "image", image_seconds, image_timings)
    console.print(totals)
    if markdown_page_timings or image_timings:
        console.print(distribution)
    console.print("Per-unit values include an equal share of shared phase overhead.", style="dim")
    console.print("When pages are batched, batch time is divided evenly across its pages.", style="dim")


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line argument parser."""
    parser = argparse.ArgumentParser(
        prog="pdf2md-unlimited-ocr",
        description="Convert PDF files to Markdown with local Unlimited OCR on Apple Silicon.",
    )
    parser.add_argument("pdfs", nargs="+", type=input_path, metavar="PDF")
    parser.add_argument("--stdout", action="store_true", help="Print Markdown instead of writing a file.")
    parser.add_argument("--force", action="store_true", help="Replace an existing Markdown file.")
    parser.add_argument("--keep-images", action="store_true", help="Keep rendered page images.")
    parser.add_argument(
        "--no-images",
        action="store_true",
        help="Do not extract detected photos, charts, figures, maps, and complex tables.",
    )
    parser.add_argument(
        "--describe-images",
        action="store_true",
        help="Add local multimodal descriptions below extracted visuals.",
    )
    parser.add_argument(
        "--image-model",
        default=DEFAULT_IMAGE_MODEL,
        help=f"Multimodal model used by --describe-images. Default: {DEFAULT_IMAGE_MODEL}.",
    )
    parser.add_argument("--dpi", type=int, default=300, help="PDF render resolution. Default: 300.")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"Hugging Face model. Default: {DEFAULT_MODEL}.")
    parser.add_argument(
        "--pages-per-batch",
        type=int,
        default=DEFAULT_PAGES_PER_BATCH,
        help=f"Pages sent to each model call. Default: {DEFAULT_PAGES_PER_BATCH}.",
    )
    parser.add_argument("--quiet", action="store_true", help="Hide normal progress messages.")
    parser.add_argument("--version", action="version", version=version("pdf2md-unlimited-ocr"))
    return parser


def _validate_inputs(args: argparse.Namespace, parser: argparse.ArgumentParser) -> list[Path]:
    """Validate inputs and outputs before the model is loaded."""
    pdf_paths: list[Path] = args.pdfs
    if args.stdout and len(pdf_paths) != 1:
        parser.error("--stdout requires exactly one PDF")
    if args.dpi <= 0:
        parser.error("--dpi must be a positive integer")
    if args.pages_per_batch <= 0:
        parser.error("--pages-per-batch must be a positive integer")
    if args.describe_images and args.no_images:
        parser.error("--describe-images cannot be combined with --no-images")
    if args.describe_images and args.stdout:
        parser.error("--describe-images cannot be combined with --stdout")

    for pdf_path in pdf_paths:
        if not pdf_path.exists():
            parser.error(f"PDF does not exist: {pdf_path}")
        if not pdf_path.is_file():
            parser.error(f"PDF is not a file: {pdf_path}")
        if pdf_path.suffix.lower() != ".pdf":
            parser.error(f"Input does not have a .pdf suffix: {pdf_path}")
        if not args.stdout and markdown_path_for(pdf_path).exists() and not args.force:
            parser.error(f"Output already exists: {markdown_path_for(pdf_path)}. Use --force to replace it.")
        if not args.stdout and not args.no_images and asset_path_for(pdf_path).exists() and not args.force:
            parser.error(f"Image output already exists: {asset_path_for(pdf_path)}. Use --force to replace it.")
    return pdf_paths


def run(argv: Sequence[str] | None = None) -> int:
    """Run the command and return its process exit status."""
    parser = build_parser()
    args = parser.parse_args(argv)
    pdf_paths = _validate_inputs(args, parser)
    console = Console(stderr=True)
    conversion_started = time.perf_counter()
    image_description_seconds = 0.0
    described_image_count = 0
    total_page_count = 0
    markdown_page_work_timings: list[float] = []
    image_work_timings: list[float] = []

    try:
        shared_ocr = None
        if not args.describe_images:
            if not args.quiet:
                print(f"Loading {args.model}", file=sys.stderr)
            shared_ocr = UnlimitedOcr.load(args.model, pages_per_batch=args.pages_per_batch)

        for pdf_path in pdf_paths:
            description_loader = None
            ocr = shared_ocr
            ocr_holder: list[UnlimitedOcr] = []
            description_phase_used = False
            pdf_described_image_count = 0
            if args.describe_images:
                if not args.quiet:
                    print(f"Loading {args.model}", file=sys.stderr)
                ocr_holder.append(UnlimitedOcr.load(args.model, pages_per_batch=args.pages_per_batch))
                ocr = ocr_holder[0]

            if ocr is None:
                raise RuntimeError("OCR model was not loaded")
            task_id = None
            description_task_id = None
            previous_completed_pages = 0
            page_work_started: float | None = None
            with Progress(
                TextColumn("{task.description}"),
                BarColumn(),
                MofNCompleteColumn(),
                TextColumn("{task.fields[unit]}"),
                TimeRemainingColumn(),
                console=console,
                disable=args.quiet,
            ) as page_progress:

                def update_progress(completed: int, total: int) -> None:
                    """Create and update this PDF's page progress task."""
                    nonlocal task_id, total_page_count, previous_completed_pages, page_work_started
                    now = time.perf_counter()
                    if task_id is None:
                        task_id = page_progress.add_task(pdf_path.name, total=total, unit="pages")
                        total_page_count += total
                    newly_completed = completed - previous_completed_pages
                    if newly_completed > 0 and page_work_started is not None:
                        seconds_per_page = (now - page_work_started) / newly_completed
                        markdown_page_work_timings.extend([seconds_per_page] * newly_completed)
                    previous_completed_pages = completed
                    page_work_started = now
                    page_progress.update(task_id, completed=completed, total=total)

                if args.describe_images:

                    def load_image_describer(visual_count: int) -> ImageDescriptionCallback:
                        """Release OCR, load the image model, and return a timed callback."""
                        nonlocal description_phase_used, description_task_id, image_description_seconds
                        description_phase_used = True
                        progress_task_id = page_progress.add_task(
                            f"{pdf_path.name} image understanding",
                            total=visual_count,
                            unit="images",
                        )
                        description_task_id = progress_task_id
                        loading_started = time.perf_counter()
                        try:
                            ocr_holder[0].release()
                            ocr_holder.clear()
                            release_model_memory()
                            if not args.quiet:
                                print(f"Loading {args.image_model} for image understanding", file=sys.stderr)
                            describer = ImageDescriber.load(args.image_model)
                        finally:
                            image_description_seconds += time.perf_counter() - loading_started

                        def describe_with_progress(image_path: Path, context: str) -> str:
                            """Describe one image and advance the image progress task."""
                            nonlocal described_image_count, pdf_described_image_count
                            nonlocal image_description_seconds
                            description_started = time.perf_counter()
                            try:
                                return describer.describe(image_path, context)
                            finally:
                                description_seconds = time.perf_counter() - description_started
                                image_description_seconds += description_seconds
                                image_work_timings.append(description_seconds)
                                described_image_count += 1
                                pdf_described_image_count += 1
                                page_progress.advance(progress_task_id)

                        return describe_with_progress

                    description_loader = load_image_describer

                result = convert_pdf(
                    pdf_path,
                    ocr,
                    dpi=args.dpi,
                    keep_images=args.keep_images,
                    asset_directory=None if args.stdout or args.no_images else asset_path_for(pdf_path),
                    description_loader=description_loader,
                    progress=update_progress,
                )
                if description_task_id is not None:
                    page_progress.update(
                        description_task_id,
                        completed=pdf_described_image_count,
                        total=pdf_described_image_count,
                    )
            if args.describe_images:
                cleanup_started = time.perf_counter()
                if ocr_holder:
                    ocr_holder[0].release()
                    ocr_holder.clear()
                release_model_memory()
                if description_phase_used:
                    image_description_seconds += time.perf_counter() - cleanup_started
            if result.image_directory is not None:
                print(f"Kept page images in {result.image_directory}", file=sys.stderr)
            if result.asset_directory is not None and not args.quiet:
                print(f"Wrote visual assets to {result.asset_directory}", file=sys.stderr)
            if args.stdout:
                sys.stdout.write(result.markdown)
            else:
                output_path = markdown_path_for(pdf_path)
                output_path.write_text(result.markdown, encoding="utf-8")
                if not args.quiet:
                    print(f"Wrote {output_path}", file=sys.stderr)
        total_seconds = time.perf_counter() - conversion_started
        if not args.quiet:
            markdown_seconds = max(0.0, total_seconds - image_description_seconds)
            print_statistics(
                console,
                total_seconds=total_seconds,
                markdown_seconds=markdown_seconds,
                image_seconds=image_description_seconds,
                markdown_page_timings=allocate_phase_overhead(
                    markdown_seconds,
                    markdown_page_work_timings,
                    total_page_count,
                ),
                image_timings=allocate_phase_overhead(
                    image_description_seconds,
                    image_work_timings,
                    described_image_count,
                ),
            )
    except ConversionError as error:
        print(f"Kept page images in {error.image_directory}", file=sys.stderr)
        print(f"pdf2md-unlimited-ocr: {error}", file=sys.stderr)
        return 1
    except Exception as error:
        print(f"pdf2md-unlimited-ocr: {error}", file=sys.stderr)
        return 1
    return 0


def main() -> None:
    """Run the installed command-line program."""
    raise SystemExit(run())
