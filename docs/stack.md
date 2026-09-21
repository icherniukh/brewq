# Stack Decision

Use Python for the production implementation.

## Choice

- Language: Python 3.12+
- CLI: `argparse` initially
- Terminal output: custom small renderer using `shutil.get_terminal_size`
- Data model: dataclasses
- JSON parsing: standard library `json`
- Config parsing: `tomllib`
- Process calls: `subprocess.run`
- Packaging: `pyproject.toml` with a console script named `brewq`
- Test runner: `pytest`
- Lint/format: defer until implementation stabilizes, then add `ruff`

## Why Python

The zsh prototype proved the UX, but it is carrying too much structured-data behavior in shell and `jq`.

Python gives us:

- Testable parsing and layout.
- A real cache module.
- Safer lock handling.
- Better fallback behavior.
- Easier packaging and release.

## Initial Architecture

- `brewq.cli` - argument parsing and command dispatch.
- `brewq.options` - normalized search, ranking, output, and cache options.
- `brewq.config` - built-in defaults, config loading, environment overrides.
- `brewq.brew` - Homebrew subprocess boundary.
- `brewq.cache` - cache paths, freshness, refresh, atomic writes, locks.
- `brewq.analytics` - Homebrew analytics fetch and merge.
- `brewq.model` - formula/cask result records.
- `brewq.columns` - column definitions, aliases, spec expansion, validation.
- `brewq.render` - table rendering, wrapping, status markers, color policy.

## Output Columns

Columns are data-driven. Config defines the default column list, and `--columns` overrides it for one invocation.

Built-in columns:

- name
- type
- installs
- description
- installed
- status
- url

The renderer should compute widths once from the selected columns and result set, then clip description-like columns with an ellipsis to fit the terminal (wrapping only when the other columns alone overflow).

## Release Shape

First release can be source-installable:

```bash
python -m pip install .
```

Then add a Homebrew formula once the CLI has a tag and stable artifact.
