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

Search is the default command. There is no public `search` subcommand. A valid
user cache is cache-only. When no user cache exists, brewq reads the bundled seed
and briefly inspects local Homebrew storage for installed state.

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
brewq -u rust
brewq -v rust
brewq -c name,30d,365d,url rust
brewq --tsv -c name,30d,url ripgrep
brewq -l python
brewq -r ripgrep
```

Options:

- `-s`, `--sort FIELD`: sort by `90d` (default), `30d`, `365d`, `trending`, or `name`.
- `-t`, `--top N`: show the top N matches by the active sort field.
- `-c`, `--columns KEYS`: use an explicit comma-joined column list.
- `-u`, `--url`: add the `url` column (before `description`) to the active column set.
- `-v`, `--verbose`: show every package field (all canonical columns except `binaries`).
- `-l`, `--installed`: filter search results to packages known to be installed.
- `-r`, `--refresh`: refresh cache before searching.
- `--all`: include deprecated and disabled packages.
- `--tsv`: emit raw tab-separated rows with no header.

Rules:

- Query text matches package names, formula aliases, and descriptions.
- Raw 90-day install volume is the default ranking signal — see brewq-253. It's
  a more trustworthy default than a self-relative growth ratio, which lets
  low-volume "new package" artifacts outrank genuinely widely-used packages.
  `trending` (recent install rate vs. a package's own historical baseline)
  remains available as an explicit, demoted sort/column (`-s trending`), and
  `30d`/`365d` remain available as explicit, opt-in raw-count windows.
- Result cap precedence: `-t N`, then `output.limit` from config when > 0, then
  terminal height on a TTY (`rows - 6`, minimum 5), then no cap when piped.
- `-c` and `-v` are mutually exclusive.
- Disabled and deprecated packages are hidden when results would overflow the
  row cap; `--all` includes them. When there is no cap (piped output) they are
  kept but rank after active packages.
- Search uses the user cache or bundled seed by default. Stale data renders first,
  then schedules background repair.
- `brewq refresh` and `brewq -r QUERY` force foreground work only when explicitly requested.
- Search prints a concise cache-age disclosure to stderr. Stale cache is called
  out more visibly than fresh cache.

## Sort Fields

Sort fields resolve through short aliases:

- `90d`: aliases `90`, `i90`.
- `30d`: aliases `30`, `i30`, `installs`.
- `365d`: aliases `365`, `i365`, `y`, `year`.
- `trending`: aliases `trend`, `hot`.
- `name`: aliases `n`, `alpha`, `az`.

Default search sort is `90d` (raw `installs_90d`).

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
- `trending`
- `binaries`
- `description`
- `installed`
- `status`
- `url`

`binaries` (`bin`/`bins`) behaves differently by package type: for casks it comes
from the cask's declared artifacts and is always available; for formulae it's
populated only from a real `Cellar` scan, so it's blank until the formula is
installed.

`trending` displays as a multiplier of a package's own historical rate (`4.1x` =
4.1 times its usual monthly installs, `1.0x` = unchanged, `0.5x` = half its usual
rate). The "recent" side is anchored on the 90d window rather than a raw 30d
snapshot. There is no hard ceiling — see `Package.trending` in `model.py` for
the pseudocount smoothing that keeps low-volume noise from reading as a huge
swing, and the maturity-scaled pseudocount that keeps packages new to
Homebrew analytics tracking (little or no install history before their most
recent 90d window) from reading as a real adoption spike.

Useful aliases:

- `n` -> `name`
- `t` -> `type`
- `v`, `ver` -> `version`
- `30`, `30d`, `i30`, `installs` -> `installs_30d`
- `90`, `90d`, `i90` -> `installs_90d`
- `365`, `365d`, `i365`, `y`, `year` -> `installs_365d`
- `trend`, `hot`, `pop`, `popularity`, `score`, `rank` -> `trending`
- `bin`, `bins` -> `binaries`
- `d`, `desc` -> `description`
- `i`, `inst` -> `installed`
- `h`, `home`, `homepage` -> `url`

`auto` is a config-only pseudo-column: at render time it resolves to whichever of
`installs_90d`/`installs_30d`/`installs_365d` has data for the top-ranked result.
The built-in default no longer needs it (it shows a literal `installs_90d`
column), but it remains available for a user's own `config.toml` `output.columns`
list.

Column shortcuts:

- `-u` adds `url` to the active column set, inserted before `description`.
- `-v` expands to the full field set: `name,type,version,installed,status,30d,90d,365d,trending,url,description`.

Default column sets (config-backed):

- Search: `name,installs_90d,trending,description`
- List: `name,type,version,description`

Colors are theme-relative: formula and cask names use standard 16-color ANSI
codes (cyan / magenta) so they follow the user's terminal theme rather than
pinned 256-color values. Color is disabled when output is not a TTY or when
`NO_COLOR` is set.

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
brewq list -u
brewq list -v
brewq list -c name,type,version
brewq list --tsv -c name,type,version
```

Options:

- `--analytics`: show cached analytics columns.
- `-c`, `--columns KEYS`: use an explicit comma-joined column list.
- `-u`, `--url`: add the `url` column.
- `-v`, `--verbose`: show every package field.
- `--limit N`: cap installed rows.
- `--tsv`: emit raw tab-separated rows with no header.

Default behavior:

- installed formulae and casks are shown together
- rows sort by type, then name
- no Homebrew subprocess or network fetch
- `--analytics` inserts `90d` before `DESCRIPTION` if no install metric column is already selected
- cache age is disclosed on stderr

## Refresh

```bash
brewq refresh
brewq refresh --force
brewq -r ripgrep
```

Fresh commands do not schedule or perform refresh work. Seed-backed and stale
commands render first, then schedule one detached worker. The worker waits five
minutes, gates on normalized system load, and avoids duplicate work through cache
state and locks.

Explicit refresh is an optional foreground Homebrew boundary for recovery and
diagnostics. It is not part of installation or normal cache maintenance.

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
sort = "90d"

[output]
columns = ["name", "installs_90d", "trending", "description"]
limit = 0  # 0 = adaptive: terminal height on a TTY, no cap when piped

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
- vary explicit column layout
- print the generated `brewq ...` command before rendering
- use the normal search, rank, column, and renderer paths

Keep this command small. It should help test layouts and spark ideas without changing the first-release product promise.
