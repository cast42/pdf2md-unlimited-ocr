"""Command-line entry point for PDF to Markdown conversion."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from importlib.metadata import version
from pathlib import Path

from .converter import ConversionError, convert_pdf, markdown_path_for
from .ocr import DEFAULT_MODEL, UnlimitedOcr


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line argument parser."""
    parser = argparse.ArgumentParser(
        prog="pdf2md-unlimited-ocr",
        description="Convert PDF files to Markdown with local Unlimited OCR on Apple Silicon.",
    )
    parser.add_argument("pdfs", nargs="+", type=Path, metavar="PDF")
    parser.add_argument("--stdout", action="store_true", help="Print Markdown instead of writing a file.")
    parser.add_argument("--force", action="store_true", help="Replace an existing Markdown file.")
    parser.add_argument("--keep-images", action="store_true", help="Keep rendered page images.")
    parser.add_argument("--dpi", type=int, default=300, help="PDF render resolution. Default: 300.")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"Hugging Face model. Default: {DEFAULT_MODEL}.")
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

    for pdf_path in pdf_paths:
        if not pdf_path.exists():
            parser.error(f"PDF does not exist: {pdf_path}")
        if not pdf_path.is_file():
            parser.error(f"PDF is not a file: {pdf_path}")
        if pdf_path.suffix.lower() != ".pdf":
            parser.error(f"Input does not have a .pdf suffix: {pdf_path}")
        if not args.stdout and markdown_path_for(pdf_path).exists() and not args.force:
            parser.error(f"Output already exists: {markdown_path_for(pdf_path)}. Use --force to replace it.")
    return pdf_paths


def run(argv: Sequence[str] | None = None) -> int:
    """Run the command and return its process exit status."""
    parser = build_parser()
    args = parser.parse_args(argv)
    pdf_paths = _validate_inputs(args, parser)

    try:
        if not args.quiet:
            print(f"Loading {args.model}", file=sys.stderr)
        ocr = UnlimitedOcr.load(args.model)

        for pdf_path in pdf_paths:
            if not args.quiet:
                print(f"Converting {pdf_path}", file=sys.stderr)
            result = convert_pdf(pdf_path, ocr, dpi=args.dpi, keep_images=args.keep_images)
            if result.image_directory is not None:
                print(f"Kept page images in {result.image_directory}", file=sys.stderr)
            if args.stdout:
                sys.stdout.write(result.markdown)
            else:
                output_path = markdown_path_for(pdf_path)
                output_path.write_text(result.markdown, encoding="utf-8")
                if not args.quiet:
                    print(f"Wrote {output_path}", file=sys.stderr)
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
