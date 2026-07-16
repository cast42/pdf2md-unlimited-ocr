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
4. Removes model control markers from the returned Markdown.
5. Writes the Markdown and removes the temporary images.

The `--keep-images` option keeps the temporary directory and prints its path to standard error.

The model stays loaded while the tool processes every page. One page is sent per model call by default. The tool inserts page breaks itself, blocks repeated output, and rejects output that reaches the token limit. Use `--pages-per-batch` to change the batch size when you need to test multi-page inference.

## Test

Run the full test suite:

```sh
just test
```

Run `just test` to call `scripts/download-test-data.fish` before pytest starts. The script saves publication 14159 from the Flemish government website as `data/14159.pdf`. Git ignores the `data` directory. If the file already exists, the script does not download it again.

The full suite converts this 22 page PDF with the real Unlimited OCR model. The regression test checks that every page is present and that the false `1. 2. 3.` preamble does not return.

The first test run downloads the model if it is not cached. The test also needs direct access to the Mac Metal GPU.

Download the PDF fixture without running the tests:

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
