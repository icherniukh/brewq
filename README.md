# brewq

`brewq` is a read-only Homebrew query and analytics tool. It answers a narrow question well: *what does Homebrew know about this package, and what should I trust?*

Install analytics are surfaced at the exact moment you search, compare, or review installed packages — so you can judge trust and quality without opening formula pages one by one.

## Install

```bash
uv tool install .
```

Ships two entry points: `brewq` and `bq` (same as `ripgrep`/`rg`).

## Usage

Search is the root command:

```bash
brewq ripgrep
brewq terminal multiplexer
brewq -t 10 json
brewq -s 365d rust
```

Sort by raw 90-day install volume by default (most trustworthy signal), or switch to `30d`, `365d`, `trending`, or `name`.

### Presets

Three built-in column presets, accessible by name or single digit:

```bash
brewq -p 1 ripgrep       # compact: name, 90d, description
brewq -p 2 ripgrep       # full: all columns
brewq -p 3 ripgrep       # links: name, url, description
```

Or pick exact columns:

```bash
brewq -c name,90d,trending,url ripgrep
```

### Installed packages

```bash
brewq list               # installed formulae and casks
brewq list --analytics   # add 90d install counts
brewq list -p 2          # full preset
```

### Scripting

```bash
brewq --tsv -c name,90d,url ripgrep
brewq list --tsv -c name,type,version
```

### Cache

Releases bundle a seed cache, so the first query renders immediately. On first use, `brewq` overlays installed state from the local Cellar and Caskroom. Stale cache renders instantly and schedules one delayed background refresh. Cache age is shown on stderr.

```bash
brewq refresh            # force cache refresh
brewq -r ripgrep         # refresh before searching
brewq config path        # show config file location
```

## Config

Optional `config.toml` at `~/.config/brewq/config.toml` (or `$BREWQ_CONFIG`):

```toml
[search]
sort = "90d"

[output]
columns = ["name", "installs_90d", "trending", "description"]
limit = 0

[list]
columns = ["name", "type", "version", "description"]

[cache]
max_age_seconds = 86400
```

Environment: `BREWQ_CONFIG`, `BREWQ_CACHE_DIR`, `BREWQ_CACHE_MAX_AGE`, `NO_COLOR`.

## What it's not

`brewq` is not a package manager. It does not install, uninstall, upgrade, manage services, or replace Brewfile workflows. It is read-only.

## Documentation

- `docs/vision.md` — product goals and non-goals
- `docs/product-spec.md` — requirements and first-release scope
- `docs/cli-design.md` — command surface, options, columns, config model
- `docs/local-workflows.md` — dotfiles aliases/functions this tool absorbs

## Repository Layout

- `src/brewq/` — Python package
- `tests/` — test suite
- `scripts/` — verify, bump, benchmark, seed cache build
- `legacy/bsx-prototype.zsh` — shell prototype (provenance)
