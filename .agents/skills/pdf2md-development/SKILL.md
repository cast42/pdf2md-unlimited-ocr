---
name: pdf2md-development
description: Develop and maintain pdf2md-unlimited-ocr. Use for code, dependency, test, documentation, command line, PDF rendering, OCR, MLX VLM, image extraction, or Markdown conversion changes in this repository.
---

# PDF2MD development

## Prepare the repository

1. Inspect the working tree and preserve changes that are outside the task.
2. Confirm that `uv` is available.
3. Run `just install` in a fresh clone or after dependency changes. The command synchronizes development dependencies, exports `pylock.toml`, and installs the pre-commit hooks.

## Manage dependencies

- Add a runtime dependency with `uv add <package>`.
- Add a development dependency with `uv add --dev <package>`.
- Keep `pyproject.toml`, `uv.lock`, and `pylock.toml` in sync.
- Run `just check` and `just test` after dependency changes.

## Use project commands

- Run all checks with `just check`.
- Run all tests with `just test`.
- Run selected pytest arguments with `just test <args>`.
- Run Ruff fixes with `just lint <args>`.
- Run type checking with `just typing <args>`.
- Build the documentation with `just docs`.
- Run the CLI with `just run <args>`.
- Download test fixtures with `just download-test-data`.
- Refresh locked dependencies with `just update`, then run `just install`.

## Follow implementation rules

- Use `pypdfium2` for PDF rendering. Do not add PyMuPDF or import `fitz`.
- Keep local model use compatible with Apple Silicon and MLX VLM.
- Keep type hints and concise docstrings current.
- Prefer built-in collection types over old `typing` aliases.
- Update tests and user documentation with behavior changes.

## Validate the change

1. Run focused tests while iterating.
2. Run `just check` before completion.
3. Run `just test` when the change affects runtime behavior, dependencies, shared conversion code, or model integration.
4. State when a full integration test could not run because Metal or a cached model was unavailable.
5. Summarize the commands and results in the final response.
