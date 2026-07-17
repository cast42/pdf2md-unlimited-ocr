# pdf2md-unlimited-ocr

`pdf2md-unlimited-ocr` converts PDF files to Markdown on an Apple Silicon Mac. It renders pages with PDFium and runs Baidu Unlimited OCR locally through MLX. PDF content is not sent to an OCR service.

## Requirements

The first version is made for this system:

- An Apple Silicon Mac
- macOS
- Python 3.14
- About 7 GB of free disk space for the model cache
- Enough free unified memory to load and run the model

The project uses `pypdfium2`. It does not use PyMuPDF or `fitz`.

## Install

Install the project and its development tools with `uv`:

```sh
just install
```

The first conversion downloads `baidu/Unlimited-OCR` from Hugging Face. The download is about 6.7 GB. Later conversions use the normal Hugging Face cache.

## Use

Convert one PDF and write `report.md` beside it:

```sh
uv run pdf2md-unlimited-ocr report.pdf
```

Detected photos, charts, figures, maps, and large complex tables are cropped into
`report_assets` and linked from `report.md`. Complex tables retain their searchable
OCR representation and include the crop as a visual fallback. Use `--no-images`
when you only need text and tables.

Add a short description below every extracted visual:

```sh
uv run pdf2md-unlimited-ocr --describe-images report.pdf
```

Quote paths that contain spaces. The `just run` wrapper preserves quoted paths,
and the CLI expands a leading `~` even when the path is quoted:

```sh
just run --describe-images "~/Downloads/AI_trainingsinfo/Werking zeesluis.pdf"
```

Image understanding uses `mlx-community/gemma-4-12B-it-qat-4bit` by default. The
model runs locally through MLX VLM. Each description appears below its image as
`**Image understanding:**`. Use `--image-model` to select another compatible
multimodal model.

The tool finishes OCR and releases the OCR model before loading Gemma 4. The two
models are not kept in memory together. Gemma 4 is not loaded when OCR finds no
visuals to describe.

Convert several PDFs:

```sh
uv run pdf2md-unlimited-ocr report.pdf appendix.pdf
```

Print one conversion to standard output:

```sh
uv run pdf2md-unlimited-ocr --stdout report.pdf
```

Keep the rendered page images:

```sh
uv run pdf2md-unlimited-ocr --keep-images report.pdf
```

Replace an existing Markdown file:

```sh
uv run pdf2md-unlimited-ocr --force report.pdf
```

Run `uv run pdf2md-unlimited-ocr --help` to see every option.

## How conversion works

For each PDF, the tool:

1. Creates a temporary directory.
2. Renders each page as a numbered PNG image with PDFium.
3. Processes each page through `baidu/Unlimited-OCR` with MLX-VLM.
4. Uses the grounded layout to retain reading order, headings, tables, and visual regions.
5. Removes repeated headers, footers, page numbers, and model control markers.
6. Writes the Markdown and visual assets, then removes the temporary page images.

The `--keep-images` option keeps the temporary directory and prints its path to standard error.

The command shows a Rich progress bar with the number of completed pages and the estimated time remaining. Use
`--quiet` to hide it. Progress is written to standard error, so `--stdout` still emits only Markdown on standard output.

When `--describe-images` is enabled and OCR finds visuals, a second Rich progress
bar shows completed image descriptions. After a successful command, a Rich table
reports total processing time, time per page, Markdown conversion time, and image
description time. The table labels Markdown statistics as per page and image
description statistics as per image. It includes the average, minimum, p25, p50,
p75, and maximum time. Model loading, rendering, output, and cleanup remain part of
their matching phase and are divided evenly across that phase's pages or images.
When `--pages-per-batch` is greater than one, each batch's time is divided evenly
across the pages in that batch.
Use `--quiet` to hide the progress bars and statistics.

The OCR model stays loaded while the tool processes every page. One page is sent per model call by default. Every batch uses the documented PDF settings. The prompt is `Multi page parsing.`, and the model uses base image mode with a 1,024 pixel image size. Generation uses a temperature of 0.0 and an output limit of 32,768 tokens. The tool inserts page breaks itself. It applies the optional 35 token repetition guard with a 1,024 token window and rejects output that reaches the token limit. Use `--pages-per-batch` to change the batch size when you need to test multi-page inference.

## Test

Run the full test suite:

```sh
just test
```

Run `just test` to call `scripts/download-test-data.fish` before pytest starts. The script saves publication 14159 as `data/14159.pdf`. It also downloads the Traffic Safety Plan 2026 to 2030 and extracts pages 1, 21, 29, and 59 to `data/vvp-layout-sample.pdf`. Git ignores the `data` directory. The script reuses files that already exist.

The full suite converts this 22 page PDF with the real Unlimited OCR model. The regression test checks that every page is present and that the false `1. 2. 3.` preamble does not return.

The first test run downloads the model if it is not cached. The test also needs direct access to the Mac Metal GPU.

Download and extract the PDF fixtures without running the tests:

```sh
just download-test-data
```

Run all quality checks:

```sh
just check
```

## Project specification

See [project.md](project.md) for the full behavior and acceptance criteria.

## Main components

- `renderer.py` renders PDF pages with `pypdfium2`.
- `ocr.py` loads and runs Unlimited OCR through MLX-VLM.
- `converter.py` controls temporary files and conversion.
- `markdown.py` cleans the model output.
- `cli.py` implements the installed command.

## References

- [Baidu Unlimited OCR](https://huggingface.co/baidu/Unlimited-OCR)
- [MLX-VLM Unlimited OCR support](https://github.com/Blaizzy/mlx-vlm/blob/main/mlx_vlm/models/unlimited_ocr/README.md)
- [pypdfium2 documentation](https://pypdfium2.readthedocs.io/)
