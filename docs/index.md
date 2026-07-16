# pdf2md-unlimited-ocr

`pdf2md-unlimited-ocr` converts PDF files to Markdown locally on an Apple Silicon Mac. It uses PDFium for page rendering and Baidu Unlimited OCR through MLX-VLM for document parsing.

## Run the command

```sh
uv run pdf2md-unlimited-ocr report.pdf
```

Use `--stdout` to print one PDF as Markdown. Use `--keep-images` to retain the rendered page images. Use `--force` to replace an existing Markdown file.

The tool processes one rendered page per model call by default. It keeps the model loaded, inserts page breaks itself, blocks repeated output, and rejects incomplete output.

## Run the tests

```sh
just test
```

Run the test command to download publication 14159 from the Flemish government website into the ignored `data` directory. The test then converts the 22 page PDF with the local OCR model and checks that the false numbered preamble does not return.

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
