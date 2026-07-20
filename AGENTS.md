# Project instructions

## Project

- The project converts PDFs to Markdown with Baidu Unlimited OCR and MLX VLM.
- Full model runs require an Apple Silicon Mac with Metal access.
- Use `uv` for Python environments and dependencies. Use the `justfile` for project commands.

## Required rules

- Use the `pdf2md-development` skill for code, dependency, test, and documentation changes.
- Render PDFs with `pypdfium2`. Do not add PyMuPDF or import `fitz`.
- Keep type hints and concise docstrings in maintained Python code.
- Prefer built-in collection types such as `list` and `dict` over old `typing` aliases.
- Treat Ruff, Ruff format, Ty, pytest, and repository hygiene warnings as failures.
- Preserve unrelated user changes in the working tree.

## Completion

- Run checks and tests that match the change.
- Update documentation when behavior or commands change.
- Report the commands run, their results, and any checks that could not be completed.
