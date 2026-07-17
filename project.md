# pdf2md-unlimited-ocr

## Purpose

`pdf2md-unlimited-ocr` is a local command line tool that converts one or more PDF files to Markdown. It is designed for a MacBook Pro with an Apple M4 processor and 24 GB of unified memory. It does not call a hosted OCR service.

The project uses Python 3.14. It uses PDFium to render PDF pages and MLX to run the OCR model on Apple Silicon.

## Main requirements

The tool must:

- Accept one or more PDF paths as command line arguments.
- Check that every input exists, is a regular file, and has a `.pdf` suffix.
- Render every page of each PDF as a separate PNG image.
- Store the page images in a temporary directory while processing the PDF.
- Use `pypdfium2` for PDF rendering.
- Never use PyMuPDF or its `fitz` module.
- Load `baidu/Unlimited-OCR` from Hugging Face.
- Run the model locally with MLX-VLM on Apple Silicon.
- Use the MLX-VLM Python API. The tool must not start a vLLM, SGLang, or other model server.
- Preserve page order from the PDF through OCR and Markdown output.
- Preserve grounded reading order and promote detected titles to Markdown headings.
- Save detected photos, charts, figures, maps, and large tables as linked visual assets.
- Keep searchable OCR for large tables and include a visual crop as a quality fallback.
- Remove running headers, footers, page numbers, and duplicate grounded blocks.
- Delete temporary page images after each PDF is processed.
- Keep the temporary page images when the user passes `--keep-images`.
- Write Markdown files beside the source PDFs by default.
- Print Markdown to standard output when the user passes `--stdout`.

## Supported system

The first version supports this system:

- Apple Silicon Mac
- Apple M4 processor
- 24 GB unified memory
- macOS
- Python 3.14

CUDA and NVIDIA GPU support are outside the first version. CPU inference and Intel Macs are also outside the first version.

Python 3.14 compatibility must be checked when dependencies are added. The implementation must not silently change the Python version.

## Main dependencies

The runtime dependencies are:

- `pypdfium2` for rendering PDF pages as images
- `mlx-vlm` version 0.6.5 or newer for Unlimited OCR support on Apple Silicon
- `mlx` as the local array and model runtime
- `transformers` for the Hugging Face tokenizer and model support used by MLX-VLM
- `Pillow` for image handling required by the model stack

The exact versions are locked with `uv`. The project uses the existing `uv` workflow from the boilerplate.

## OCR model

The default model is `baidu/Unlimited-OCR` from Hugging Face.

MLX-VLM can load the original Baidu model directly. The first version must not depend on a community conversion or quantized copy of the model. A model option may be added so a user can test another compatible Hugging Face model later.

The model must be loaded once when the command starts and reused for every input PDF in that command.

For PDF input, the tool must use these model settings:

- Prompt: `Multi page parsing.`
- Image mode: `base`
- Cropping: disabled
- Image size: 1024
- Base size: 1024
- Temperature: 0.0
- Maximum output: 32,768 tokens
- Repetition n-gram size: 35
- Repetition window: 1,024 for PDF page batches

The model must remain loaded while the tool processes a PDF. The default batch size is one page so the program controls every page boundary and each page gets its own output budget. The generated text must be treated as Markdown.

The program must reject a batch when the model reaches the output token limit or generates a long run of repeated empty table cells. It must remove text emitted before the first grounded layout marker.

## PDF rendering

The tool must open each PDF with `pypdfium2` and render every page at 300 DPI by default. A `--dpi` option must let the user choose another positive DPI value.

Page files must use zero-padded names so lexical order matches PDF page order:

```text
page_0001.png
page_0002.png
page_0003.png
```

The renderer must close PDF pages and documents as soon as they are no longer needed.

## Temporary files

Each input PDF gets its own temporary directory. Normal processing must use a system temporary location.

The program must remove the directory and all rendered page images after the Markdown has been written. Cleanup must also run when model loading, rendering, OCR, or output writing fails.

When `--keep-images` is present, the program must keep the directory and print its absolute path to standard error. The path must never be printed to standard output because standard output may contain Markdown.

## Markdown output

The default output path is beside the input PDF and uses the same base name with a `.md` suffix.

```text
report.pdf  ->  report.md
scan.PDF    ->  scan.md
```

The command must refuse to replace an existing Markdown file unless the user passes `--force`.

The program must clean model control tokens from the generated text. It must:

- Remove beginning, end, and padding tokens.
- Remove layout detection wrappers and their coordinates while keeping the recognized text.
- Replace each `<PAGE>` token with a Markdown page break comment.
- End every Markdown output with one newline.

When `--stdout` is present, the command accepts exactly one PDF. Markdown is the only content written to standard output. Progress, kept image paths, warnings, and errors must go to standard error.

## Command line interface

The installed command is `pdf2md-unlimited-ocr`.

Planned usage:

```text
pdf2md-unlimited-ocr [OPTIONS] PDF [PDF ...]
```

Planned options:

- `--stdout` prints Markdown instead of writing a file. It requires one input PDF.
- `--force` replaces an existing Markdown file.
- `--keep-images` keeps rendered page images and reports their directory.
- `--no-images` disables extraction of visual assets.
- `--dpi INTEGER` sets the render resolution. The default is 300.
- `--model MODEL_ID` selects a compatible Hugging Face model. The default is `baidu/Unlimited-OCR`.
- `--pages-per-batch INTEGER` sets the number of pages in each model call. The default is 1.
- `--quiet` hides normal progress messages. Errors are still shown.
- `--version` prints the installed program version.
- `--help` prints command help.

Example commands:

```sh
pdf2md-unlimited-ocr report.pdf
pdf2md-unlimited-ocr report.pdf appendix.pdf
pdf2md-unlimited-ocr --stdout report.pdf
pdf2md-unlimited-ocr --keep-images --force scan.pdf
```

## Processing flow

For each command, the program must:

1. Parse and validate all command line arguments.
2. Check every planned output before starting expensive model work.
3. Load the tokenizer, processor, and model once.
4. Process each PDF in the order given by the user.

For each PDF, the program must:

1. Create a temporary directory.
2. Render all pages to ordered PNG files with `pypdfium2`.
3. Pass ordered page batches to Unlimited OCR through MLX-VLM.
4. Clean the generated Markdown.
5. Write the Markdown to its final destination.
6. Delete the temporary directory unless `--keep-images` is present.

## Errors and exit status

The command must return a nonzero exit status when any PDF fails. Error messages must name the PDF and explain the failed stage.

Expected error cases include:

- A missing or unreadable input file
- A path that is not a PDF
- An invalid or password protected PDF
- A PDF with no pages
- An invalid DPI value
- An output file that already exists
- A model download or loading failure
- Insufficient memory during inference
- A rendering or OCR failure
- An output write failure

When several PDFs are supplied, the first version stops at the first failure. Files completed before the failure remain in place.

## Privacy and downloads

PDF content and rendered page images must stay on the local Mac. Expected network access includes the model download from Hugging Face and the public regression PDF downloaded by the test data script.

The documentation must explain the model download size and cache location before release. The tool must use the normal Hugging Face cache instead of storing model weights inside the project.

## Testing

Unit tests must replace MLX-VLM calls with test doubles. The full test command also downloads the public regression fixture from `https://publicaties.vlaanderen.be/view-file/14159` and runs it through the real model on MLX. The fixture is stored as `data/14159.pdf`.

The test data script must also download the Traffic Safety Plan 2026 to 2030. It must use PDFium to extract source pages 1, 21, 29, and 59 in that order to `data/vvp-layout-sample.pdf`. The complete `data` directory must be ignored by Git.

The test suite must cover:

- Input validation
- Output path generation
- Existing output protection
- PDF page ordering
- Temporary directory cleanup after success
- Temporary directory cleanup after failure
- `--keep-images` behavior
- Standard output isolation
- Model loading once for several PDFs
- Markdown control token cleanup
- Exit status and error messages

The integration test must confirm that all 22 pages of the regression fixture are converted and that the false numbered preamble does not appear. It requires an Apple Silicon Mac and may download the model when it is not already cached.

## Acceptance criteria

The first version is complete when:

- `uv sync` installs the project on the target Mac with Python 3.14.
- The command converts a text PDF and a scanned PDF to readable Markdown.
- Several PDF arguments produce separate Markdown files.
- `--stdout` produces clean Markdown for one PDF.
- The implementation imports no PyMuPDF or `fitz` code.
- Temporary page images are removed by default.
- `--keep-images` preserves the page images and reports their location.
- Tests, lint checks, type checks, and the documentation build pass.

## References

- [Baidu Unlimited OCR](https://huggingface.co/baidu/Unlimited-OCR)
- [Unlimited OCR source repository](https://github.com/baidu/Unlimited-OCR)
- [MLX-VLM Unlimited OCR documentation](https://github.com/Blaizzy/mlx-vlm/blob/main/mlx_vlm/models/unlimited_ocr/README.md)
- [pypdfium2 documentation](https://pypdfium2.readthedocs.io/)
