# brewq

`brewq` is a read-only Homebrew query and analytics tool: find packages, compare
install counts, and inspect installed formulae and casks. It does not install,
upgrade, uninstall, manage services, or manage Brewfiles.

## Install and run

Requires Python 3.12+ and Homebrew for local inventory and refresh operations.

```sh
uv tool install .
brewq ripgrep
bq ripgrep
```

`brewq` and `bq` are identical entry points. Use `uv run brewq` in a checkout to
run its source rather than an older user-level installation. After verifying an
updated build, `uv tool install --force .` replaces the installed copy. Compare
`brewq --version` with `uv run brewq --version` when diagnosing drift.

## Search and output

```sh
brewq terminal multiplexer
brewq -t 10 json
brewq -s 365d rust
brewq -c name,90d,url ripgrep
brewq --tsv -c name,90d,url ripgrep
```

`brewq --help` shows the common search path. `brewq --full-help` adds the full
column reference plus concise trending and cache behavior.

Search matches names, formula aliases, and descriptions. All query terms must
match; name normalization and a narrow formula fuzzy fallback also apply.
The default sort is raw 90-day install volume. Exact name/alias matches precede
other active matches under metric sorts; disabled/deprecated results rank last.
`-s name` sorts alphabetically within those status groups.

| Search option | Current behavior |
| --- | --- |
| `-s`, `--sort FIELD` | `90d` (built-in default), `30d`, `365d`, `trending`, or `name` |
| `-t`, `--top N` | Positive result cap; overrides configuration and terminal sizing |
| `-l`, `--installed` | Filter to packages marked installed |
| `-r`, `--refresh` | Force foreground refresh before searching |
| `--all` | Retain deprecated/disabled matches when the cap would otherwise hide them |

Search cap precedence is `-t`, then positive `output.limit`, then terminal rows
minus six (minimum five) on a TTY, then unlimited when piped. This caps records,
not wrapped terminal lines. When capped matches overflow, deprecated/disabled
matches are hidden unless `--all` is given. Otherwise they remain, ranked last.

These output options work for both search and `list`:

| Output option | Current behavior |
| --- | --- |
| `-c`, `--columns COLS` | Select fields, edit the layout with `+`/`-`, or use `all` / `help` |
| `--tsv` | Selected columns as raw tab-separated rows, without a header |

Canonical columns are `name`, `type`, `version`, `installs_30d`, `installs_90d`,
`installs_365d`, `trending`, `binaries`, `description`, `installed`, `status`, and
`url`. Use `30d`, `90d`, and `365d` as short metric names. `bin`/`bins`, `desc`,
and `home`/`homepage` are also accepted. `trend` and `hot` mean `trending`.
Prefer canonical names in scripts; ambiguous popularity/score/rank aliases are
rejected.

Discover fields or adjust a layout without retyping it:

```sh
brewq -c help                       # field reference and short names; no cache needed
brewq ripgrep -c +version,bin        # keep your layout, add version and binaries
brewq rust -c +home,-trend           # add homepage, remove trend
brewq rust -c=-desc                  # remove description; = protects the leading minus
brewq list -c +90d,trend             # extend the installed-package layout
brewq ripgrep -c all --tsv           # every field, with raw values
brewq ripgrep -c name,version,90d    # exact selection and order
```

An initial `+` or `-` edits the command's configured layout. Comma-separated
fields keep the preceding operation until another `+` or `-` switches it.
Added fields go before description (or at the end if description is absent);
adding an existing field or removing an absent one has no effect. Aliases resolve
before editing, so `+90d` won't duplicate `installs_90d`. Keep at least one field.
`-c default` selects the configured layout. The same controls work with `list`.

Cask binaries come from declared artifacts; formula binaries require local
installed data.

Search defaults to `name,90d,trending,description`; list defaults to
`name,type,version,description`. `trending` is a smoothed recent-to-historical
installation-rate multiplier, not absolute popularity. It is currently visible
by default but is not the default sort.

TREND adds compact momentum cues: `↑↑` at 2.0× or above, `↑` at 1.2× or
above, `·` near baseline, and `↓` below 0.8×. Rising values are green on a
color terminal, with bold emphasis at 2.0×; steady, cooling, and missing values
are subdued. Bands use the displayed one-decimal multiplier, not statistical
significance thresholds.
Markers remain visible without color; TSV keeps the raw multiplier.

`--tsv` is the only machine-readable format. Cells sanitize tabs and newlines;
unknown install counts become empty cells. Table colors follow the terminal
theme, are TTY-only, and honor a nonempty `NO_COLOR` value. Installed markers
remain visible without color.

## Installed packages

```sh
brewq list
brewq list -c name,type,version,90d,description
brewq list --limit 10
brewq list --tsv -c name,type,version
```

Rows sort by type, then name. `--limit N` accepts a positive cap. Select cached
analytics through the same `-c` column interface used by search; this never
fetches analytics on demand. VERSION displays the installed version for installed
rows; the catalog's available version remains separate internally.

## Cache and recovery

The cache footer uses subdued neutral text on a color terminal. Age, incomplete
analytics, and refresh scheduling remain visible without red freshness accents.

Releases bundle a seed catalog. Loads validate the user snapshot before using it,
fall back to the seed after corruption, and reconcile installed state from local
Homebrew roots. A successful empty inventory clears stale installed markers;
missing or unreadable roots preserve the last known state. Stale, seed, and
incomplete snapshots can schedule a detached refresh with a five-minute delay
and system-load checks. Cache information goes to stderr after rows are flushed.

Snapshots record analytics completeness independently of file age. If metadata
refresh succeeds while analytics is unavailable, brewq retains usable counts
from the previous snapshot, marks the new snapshot for repair, and retries after
the scheduler cooldown. JSON, pickle, and scheduler state use atomic replacement.

```sh
brewq refresh           # refresh if stale
brewq refresh --force   # force recovery, including a recently corrupted cache
brewq -r ripgrep        # force refresh, then search
brewq config path
```

`update-cache` remains a compatibility alias for `refresh`. `random [--seed N]`
remains a development layout lab, not a product discovery workflow.

## Configuration

Configuration lives at `${XDG_CONFIG_HOME:-~/.config}/brewq/config.toml`, unless
`BREWQ_CONFIG` overrides it. Built-in defaults:

```toml
[search]
sort = "90d"

[output]
columns = ["name", "installs_90d", "trending", "description"]
limit = 0 # terminal-height cap on a TTY; unlimited when piped

[list]
columns = ["name", "type", "version", "description"]

[cache]
max_age_seconds = 86400
```

`BREWQ_CACHE_DIR` overrides the cache directory, otherwise
`${XDG_CACHE_HOME:-~/.cache}/brewq` is used. `BREWQ_CACHE_MAX_AGE` overrides cache
age in seconds. There are no preset-management commands or named column presets.

The `auto` pseudo-column in search output configuration selects an available raw
metric from the top result, preferring 90d, then 30d, then 365d. It is rejected
in list configuration and explicit `-c`; prefer explicit metric columns in scripts.

Invalid sections, fields, types, ranges, sort names, and columns emit a concise
stderr diagnostic and fall back field-by-field. Invalid `BREWQ_CACHE_MAX_AGE`
keeps the validated configured value. Help, version, and `config path` do not
load operational configuration.

## Stability and development

The September 2026 stabilization milestone fixed config/cache validation,
installed-state reconciliation, incomplete refresh recovery, and scheduling
before output. Independent workflow reviews found no remaining release blocker.
The 0.5.0 wheel, bundled seed, and both entry points were verified in an isolated
Python 3.12 environment; the user-level `brewq` and `bq` installation now matches.

```sh
uv sync --extra dev
uv run python scripts/verify.py
bd ready
bd list --status=in_progress
```

Verification runs Ruff, pytest, subprocess CLI smoke checks, and external
installed-entry-point parity checks. The artifact gate also builds and tests both
entry points and the bundled seed in an isolated installation.

Maintained documentation:

- [AGENTS.md](AGENTS.md): contributor workflow, ownership, and verification.
- [Design and roadmap](docs/roadmap.md): philosophy, architecture, release gates,
  and preserved historical decisions.

Source is in `src/brewq/`, tests in `tests/`, and development commands in
`scripts/`. `legacy/bsx-prototype.zsh` is preserved provenance.
