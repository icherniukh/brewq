# brewq

`brewq` is a read-only Homebrew query and analytics tool for users who want more useful package search results without opening formula pages one by one.

It is designed around a small set of workflows:

- search packages by name and description
- compare matches with install analytics as a trust signal
- choose table columns or JSON output for scripts
- list installed formulae and casks with richer metadata

`brewq` is not a Homebrew manager. It does not install, uninstall, upgrade, manage services, or replace Brewfile workflows.

## Status

This repository currently contains the product direction, CLI sketch, and a Python package scaffold. The historical shell prototype is preserved in `legacy/bsx-prototype.zsh` until replacement behavior is implemented and verified.

The Python entry point is intentionally a stub:

```bash
PYTHONPATH=src python -m brewq.cli ripgrep
```

The planned CLI shape is documented before the implementation is filled in.

For a visual project snapshot, open `docs/status-dashboard.html`.

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
