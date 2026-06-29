# brewq

`brewq` is a read-only Homebrew query and analytics tool for users who want more useful package search results without opening formula pages one by one.

It is designed around a small set of workflows:

- search packages by name and description
- compare matches with install analytics as a trust signal
- choose table columns or raw TSV output for scripts
- list installed formulae and casks with richer metadata

`brewq` is not a Homebrew manager. It does not install, uninstall, upgrade, manage services, or replace Brewfile workflows.

## Status

The historical shell prototype is preserved in `legacy/bsx-prototype.zsh` until replacement behavior is implemented and verified.

The Python entry point already covers the current core workflows:

```bash
PYTHONPATH=src python -m brewq.cli ripgrep
PYTHONPATH=src python -m brewq.cli -t 10 -s 365d rust
PYTHONPATH=src python -m brewq.cli --tsv -c name,30d,url ripgrep
PYTHONPATH=src python -m brewq.cli list --tsv -c name,type,version
PYTHONPATH=src python -m brewq.cli refresh
```

Releases include a seed cache, so the first command can render immediately. On
first use, `brewq` overlays installed state from the local Homebrew Cellar and
Caskroom. Fresh queries stay cache-only; stale data renders immediately and
schedules one delayed, low-load background refresh. Cache state is disclosed on
stderr. `brewq refresh` and `brewq -r QUERY` are optional recovery controls.

For a visual project snapshot, open `docs/status-dashboard.html`. For fresh data every time the page loads, run:

```bash
python3 scripts/serve-status-dashboard.py
```

Then open `http://127.0.0.1:8765/`. To refresh the embedded static fallback, run:

```bash
python3 scripts/update-status-dashboard.py
```

## Benchmarks

Run the lightweight benchmark harness before performance work:

```bash
python3 scripts/benchmark.py --iterations 3
python3 scripts/benchmark.py --list
```

The output is a markdown table covering cache load, ranking/filtering, table rendering, TSV rendering, and installed-list paths.

## Documentation

- `docs/vision.md` - product goals and non-goals.
- `docs/product-spec.md` - requirements and first-release scope.
- `docs/cli-design.md` - command surface, options, columns, and config model.
- `docs/status-dashboard.html` - static project status dashboard.
- `docs/local-workflows.md` - dotfiles aliases/functions this tool should absorb.
- `docs/stack.md` - stack decision and implementation shape.
- `docs/roadmap.md` - implementation and release plan.
- `docs/migration.md` - provenance and cleanup notes for existing copies.

## Repository Layout

- `legacy/bsx-prototype.zsh` - shell prototype migrated from dotfiles.
- `src/brewq/` - Python package scaffold.
- `tests/` - test directory for the implementation.
