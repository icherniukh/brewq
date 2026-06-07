# CLI Design

Keep the command surface small, but make output composition universal.

`brewq` should feel like `brew search` with better results. It should not grow a custom flag for every display tweak. Instead, columns and defaults should come from a small config model, with command-line overrides when needed.

## Command Shape

```bash
brewq [search-options] <query...>
brewq list [list-options]
brewq cache status
brewq cache refresh [--force]
brewq cache clear
brewq config path
```

Search is the default command. There should be no public `search` subcommand.

`list` is the only package-data command besides default search. It means "installed packages," matching the workflow currently covered by `brew-installed` / `brew-ll`.

## Search Options

### Essential Search

```bash
brewq ripgrep
brewq --type formula ripgrep
brewq --type cask chrome
brewq --desc terminal multiplexer
brewq -n ripgrep
brewq --json ripgrep
brewq -c name,version,installs ripgrep
brewq --columns name,type,installs,description,url ripgrep
```

Options:

- `--type formula|cask|all`
- `--desc`: search names and descriptions, replacing the shell `brew-discover`/`bsd` workflow
- `-n`, `--name`: sort by name instead of popularity
- `-y`, `--year`: show 365-day installs instead of 30-day installs
- `--json`: machine-readable output
- `-c`, `--columns LIST_OR_PROFILE`
- `--limit N`

Default:

- `--type all`
- name/token search, matching Homebrew default search scope
- popularity sort
- 30-day installs
- table output
- columns from config; the built-in default includes `version` and omits `type` because terminal output differentiates formulae and casks by entry color

Defer:

- installed-only filters
- grouping controls
- custom color controls

Those can come later if repeated use proves they are needed.

## Columns

Columns are the main extension point. They should be universal, config-backed, and shared by table and JSON output.

Column names:

- `name`
- `type`
- `version`
- `installs`
- `installs_30d`
- `installs_90d`
- `installs_365d`
- `description`
- `installed`
- `status`
- `url`

Derived aliases:

- `popularity` maps to the selected metric, initially `installs-30d` or `installs-365d`
- `homepage` aliases `url`

Column profiles:

- `default`: loaded from config
- `compact`: `name,installs,description`
- `full`: `name,type,version,installs,installed,status,url,description`

CLI behavior:

```bash
brewq ripgrep
brewq -c compact ripgrep
brewq --columns name,installs,url ripgrep
```

Rules:

- Config owns the default column list.
- `-c` / `--columns` overrides config for one invocation.
- Unknown columns are a clear user error.
- Table output renders only selected columns.
- JSON output includes selected columns by default, with a later option possible for full records if needed.
- Renderers receive normalized result objects and a list of column definitions.

## Cache Commands

```bash
brewq cache status
brewq cache refresh
brewq cache refresh --force
brewq cache clear
```

Cache command output should be plain and inspectable:

- cache path
- exists or missing
- age
- max age
- formula count
- cask count
- analytics availability
- active lock, if any

## Installed List

```bash
brewq list
brewq list --type formula
brewq list --analytics
brewq list --analytics --fetch
brewq list -c name,type,version,description
brewq list --json
```

Options:

- `--type formula|cask|all`
- `--analytics`: include analytics columns if cached
- `--fetch`: fetch missing per-package analytics
- `-c`, `--columns LIST_OR_PROFILE`
- `--limit N`
- `--json`

Default:

- installed formulae and casks
- sorted by type then name
- table output
- columns from config
- no network fetch for missing analytics

Reasoning:

- This directly replaces `brew_installed`.
- It should not duplicate all of `brew list`.
- It answers "what do I have installed and what is it?" rather than managing packages.

## Environment

Environment variables:

- `BREWQ_CACHE_DIR`
- `BREWQ_CACHE_MAX_AGE`
- `BREWQ_CONFIG`
- `NO_COLOR`

Use a cache directory instead of a single configurable file path. The tool can own multiple files cleanly:

- metadata cache
- analytics cache
- merged search index
- lock file

## Config

Config should be simple and optional. If the file is missing, built-in defaults apply.

Default path:

- `${XDG_CONFIG_HOME:-~/.config}/brewq/config.toml`

Initial config:

```toml
[search]
type = "all"
sort = "popularity"
metric = "installs-30d"

[output]
format = "table"
columns = ["name", "version", "installs", "description"]
limit = 0

[list]
columns = ["name", "version", "description"]
analytics = false

[cache]
max_age_seconds = 86400
```

`brewq config path` exists only to show where the config file would live. It should not become a large config-management subsystem.

## Compatibility Aliases

Support these prototype-compatible aliases for the first release:

- `-n`
- `-y`
- `update-cache` as an alias for `cache refresh`

Do not preserve every prototype flag forever. The Python version should define the stable interface.
