# pdf2md-unlimited-ocr

`pdf2md-unlimited-ocr` converts PDF files to Markdown locally on an Apple Silicon Mac. It uses PDFium for page rendering and Baidu Unlimited OCR through MLX-VLM for document parsing.

## Run the command

```sh
uv run pdf2md-unlimited-ocr report.pdf
```

Use `--stdout` to print one PDF as Markdown. Use `--keep-images` to retain the rendered page images. Use `--force` to replace an existing Markdown file.

## Run the tests

```sh
just test
```

The tests include a one page PDF to Markdown roundtrip with the real local OCR model.

## Python API

::: pdf2md_unlimited_ocr.main
    handler: python
    options:
      members:
        - UnlimitedOcr
        - convert_pdf
        - markdown_path_for
      show_root_heading: false
      show_source: true
