# CLI Design

Keep `brewq` small: search, list, refresh, config.

`brewq` should feel like a sharper `brew search`: readable package matches, install analytics in view, and a single column system that works for humans and scripts. It is not a Homebrew manager and should not grow install, upgrade, service, Brewfile, TUI, GUI, or product-level random-discovery behavior.

## Command Shape

```bash
brewq [search-options] <query...>
brewq list [list-options]
brewq refresh [--force]
brewq config path
brewq random [--seed N]
```

Search is the default command. There is no public `search` subcommand. Normal
search is cache-only and does not shell out to Homebrew.

`list` is the installed-package view. It uses the same column and TSV model as search, but its defaults are shaped for installed formulae and casks.

`random` is a lab command for exercising output layouts and finding inspiration while developing `brewq`. It is not the product's random package browser. It prints the generated command to stderr, then runs the normal search path.

## Search

Examples:

```bash
brewq ripgrep
brewq terminal multiplexer
brewq -t 10 json
brewq -s 365d rust
brewq -s name ripgrep
brewq -p full rust
brewq -c name,30d,365d,url rust
brewq --tsv -c name,30d,url ripgrep
brewq -l python
brewq -r ripgrep
```

Options:

- `-s`, `--sort FIELD`: sort by `30d`, `90d`, `365d`, or `name`.
- `-l`, `--installed`: filter search results to packages known to be installed.
- `-p`, `--preset NAME`: use `compact` or `full`.
- `-c`, `--columns KEYS`: use an explicit comma-joined column list.
- `-t`, `--top N`: show the top N matches by install count.
- `-r`, `--refresh`: refresh cache before searching.
- `--tsv`: emit raw tab-separated rows with no header.

Rules:

- Query text matches package names, formula aliases, and descriptions.
- Install analytics are the default ranking signal.
- Search defaults to the top 15 matches.
- `-t N` overrides the default row cap for normal "top results" use.
- `-p` and `-c` are mutually exclusive.
- Disabled and deprecated packages remain visible, but rank after active packages.
- Search uses the local cache by default; use `brewq refresh` or `brewq -r QUERY`
  when live Homebrew data should be fetched first.
- Search prints a concise cache-age disclosure to stderr. Stale cache is called
  out more visibly than fresh cache.

## Sort Fields

Sort fields resolve through short aliases:

- `30d`: aliases `30`, `i30`, `installs`, `popularity`, `pop`.
- `90d`: aliases `90`, `i90`.
- `365d`: aliases `365`, `i365`, `y`, `year`.
- `name`: aliases `n`, `alpha`, `az`.

Default search sort is `30d`.

The table header marks the active sort column when that column is visible, for example `30d ↓`.

## Columns

Columns are the main extension point. They are shared by table and TSV output.

Canonical columns:

- `name`
- `type`
- `version`
- `installs_30d`
- `installs_90d`
- `installs_365d`
- `popularity`
- `binaries`
- `description`
- `installed`
- `status`
- `url`

Useful aliases:

- `n` -> `name`
- `t` -> `type`
- `v`, `ver` -> `version`
- `30`, `30d`, `i30`, `installs` -> `installs_30d`
- `90`, `90d`, `i90` -> `installs_90d`
- `365`, `365d`, `i365`, `y`, `year` -> `installs_365d`
- `pop`, `score`, `rank` -> `popularity`
- `bin`, `bins` -> `binaries`
- `d`, `desc` -> `description`
- `i`, `inst` -> `installed`
- `h`, `home`, `homepage` -> `url`

Search presets:

- `default`: config-backed, built in as `name,installs,description`
- `compact`: `name,installs_30d,description`
- `full`: `name,type,version,installs_30d,installs_90d,installs_365d,installed,status,description`

List presets:

- `default`: config-backed, built in as `name,type,version,description`
- `compact`: `name,type,description`
- `full`: `name,type,version,installs_30d,installed,status,description`

## TSV

`--tsv` is the only public machine-readable output mode.

TSV rules:

- no header row
- selected columns only
- raw values where available
- tabs and newlines sanitized inside cells
- same records and column definitions as table output

Examples:

```bash
brewq --tsv -c name,30d,url ripgrep
brewq list --tsv -c name,type,version
```

## Installed List

Examples:

```bash
brewq list
brewq list --analytics
brewq list -p full
brewq list -c name,type,version
brewq list --tsv -c name,type,version
```

Options:

- `--analytics`: show cached analytics columns.
- `-p`, `--preset NAME`: use `compact` or `full`.
- `-c`, `--columns KEYS`: use an explicit comma-joined column list.
- `--limit N`: cap installed rows.
- `--tsv`: emit raw tab-separated rows with no header.

Default behavior:

- installed formulae and casks are shown together
- rows sort by type, then name
- no Homebrew subprocess or network fetch
- `--analytics` inserts `30d` before `DESCRIPTION` if no install metric column is already selected
- cache age is disclosed on stderr

## Refresh

```bash
brewq refresh
brewq refresh --force
brewq -r ripgrep
```

Normal commands are quick by default and do not schedule or perform refresh work.
Explicit refresh is the foreground Homebrew boundary.

`update-cache` is kept as a compatibility alias for `refresh`.

## Config

Config is optional and only controls defaults.

Default path:

```text
${XDG_CONFIG_HOME:-~/.config}/brewq/config.toml
```

Built-in defaults:

```toml
[search]
sort = "installs_30d"

[output]
columns = ["name", "installs", "description"]
limit = 15

[list]
columns = ["name", "type", "version", "description"]

[cache]
max_age_seconds = 86400
```

Environment:

- `BREWQ_CACHE_DIR`
- `BREWQ_CACHE_MAX_AGE`
- `BREWQ_CONFIG`
- `NO_COLOR`

`brewq config path` only prints the config path. It should not become a config-management subsystem.

## Lab Command

```bash
brewq random
brewq random --seed 7
```

`random` exists for local testing and design exploration:

- pick a query from a fixed term list
- vary sort field and top count
- vary preset or explicit column layout
- print the generated `brewq ...` command before rendering
- use the normal search, rank, column, and renderer paths

Keep this command small. It should help test layouts and spark ideas without changing the first-release product promise.
