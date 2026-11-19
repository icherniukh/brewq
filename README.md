# brewq

Brew client for the working class. Don't ask you nothing, speaks primarily digits: installations and trends in your face just as you like it. Read-only. Runs locally on cache.

<p align="center">
  <img src="demo.gif" alt="brewq searching the local Homebrew catalog from the terminal" width="720">
</p>

## Install

Requires Homebrew (for installed inventory and register updates).

```zsh
brew install icherniukh/tap/brewq
brewq +setup   # optional: link the `bq` shorthand
bq ripgrep
```

Or install a wheel with `uv` (Python 3.12+), or run a checkout directly:

```zsh
uv tool install path/to/brewq-*.whl
uv run brewq ripgrep   # in a checkout; compare `brewq --version` with `uv run brewq --version` to catch drift
```

`+setup` links `bq` beside `brewq` only when that name is free and is not a shell alias or function; a foreign `bq` is left unchanged. `+setup --dry-run` previews the link.

## Usage

**Compare candidates:**

```zsh
bq                              # top overall; fits the terminal height
bq -s trend                     # top rising packages
bq "ai agent"                   # description search as one phrase
bq --tsv -c name,90d,url ripgrep  # raw rows for scripts
```

```console
$ bq -t 6 grep
NAME         90d ↓    TREND  DESC
────────────────────────────────────────────────────────────────────────────────
grep         6,100  0.7x ↓   GNU grep, egrep and fgrep
ripgrep ✔   97,845  0.7x ↓   Search tool like grep and The Silver Searcher
ast-grep ✔  32,016  1.5x ↑   Code searching, linting, rewriting
semgrep     19,788  1.1x ·   Easily detect and prevent bugs and anti-patterns i…
ugrep        8,316  0.7x ↓   Ultra fast grep with query UI, fuzzy search, archi…
ack ✔        1,566  0.4x ↓   Search tool like grep, but optimized for programme…
brewq: showing 6 of 36; -a for all, -t N for a count
cache: 5h old
```

Counts vary by snapshot. The exact match (`grep`) ranks first; the rest follow the sort.

**Review installed packages:** `-i [query]` is the only installed view and follows search's sorting, caps, `-a`, `-r`, and status ranking. Its analytics come from the cache and are never fetched on demand; `VER` shows the installed version.

## Reference

`bq --help` shows the common path; `-f` (`--full-help`) adds columns, trend, and cache details; `-v` (`--version`) prints the version. Flags may appear anywhere among query terms; `+action` dispatch applies only to the first token.

| Search option | Behavior |
| --- | --- |
| `-s`, `--sort FIELD` | `90d` (built-in default), `30d`, `365d`, `trend`, or `name` |
| `-r`, `--reverse` | Reverse/bottom-up sort (redundant with `-a` on a TTY) |
| `-t`, `--top N` | Positive result cap; overrides configuration and `-a` |
| `-i`, `--installed` | Show installed packages, optionally filtered by query |
| `-u`, `--update` | Attempt a forced register refresh, then query available data |
| `-a`, `--all` | Remove the result cap; best row last on a TTY |

| Output option | Behavior |
| --- | --- |
| `-c`, `--columns COLS` | Exact ordered fields; `default` for the configured view |
| `-m`, `--tsv` | Selected columns as raw tab-separated rows, without a header |
| `-n`, `--no-color` | Suppress ANSI styling on stdout and stderr |
| `-q`, `--quiet` | Suppress routine status notes on stderr; errors and data-quality warnings still print |

### Columns

| Field | Header | Meaning |
| --- | --- | --- |
| `name` | `NAME` | Package name |
| `type` | `TYPE` | `formula` or `cask` |
| `ver` | `VER` | Installed version when present; otherwise catalog version |
| `30d`, `90d`, `365d` | same | Installs in that window (formula installs on request; cask-install feed) |
| `trend` | `TREND` | Smoothed recent rate relative to the package's earlier rate |
| `bin` | `BIN` | Executable names (declared cask binary artifacts when present; formulae require local installed data) |
| `url` | `URL` | Homepage URL |
| `desc` | `DESC` | Package description |

Field names are exact and shared by `-c`, `-s`, and configuration; typos get a suggestion, never a guess. `-c` takes one comma-separated list: `default` expands the configured view (`name,90d,trend,desc`; with `-i`, `name,desc`), duplicates keep their first position, and signed `+x`/`-x` edits are rejected with the equivalent list. `default` can change between releases, so scripts should name fields.

Tables mark installed rows with `✔` (not in `-i`), prefix `DESC` with `(deprecated)` or `(disabled)`, drop all-blank columns except `NAME` (stderr notes any you named), shorten URLs, and switch to labeled vertical records when the selection cannot fit. `trend` is shown by default but is never the default sort; its cues (`↑↑` ≥ 2x, `↑` ≥ 1.2x, `·`, `↓` < 0.8x) and `✔` survive without color. Styling is per stream and TTY-only; `-n`, `NO_COLOR`, or `TERM=dumb` turns it off.

`--tsv` is the only machine-readable format: headerless, uncapped unless `-t` is given, sanitized cells, every selected column kept (empty cells for unknown counts), full raw values, no ANSI.

### Matching, ordering & limits

Every query term must match a normalized name, formula alias, or description. Substrings, DidYouMean spelling corrections (which can add results), and Python `/regex/` queries work. An omitted or empty query selects the whole catalog (with `-i`, every installed package); empty results exit `0`. Exact name/alias matches rank first under every sort, even when inactive; other deprecated or disabled rows rank last but are never filtered out. Caps, then reversal, apply after ranking.

On a terminal the cap is `-t N`, else `-a` (unlimited, best row last), else configured `top`. `top = "auto"` fits `max(1, rows - 6)` table rows of stdout's terminal (vertical records also count wrapped lines and notices) and shows at least one row; `-t N` skips this fitting. `LINES`/`COLUMNS` apply only without a TTY. Hidden rows are reported on stderr as `showing N of M; -a for all, -t N for a count`. Pipes and TSV ignore configured `top` and `reverse`: output is uncapped and best-first unless `-t` or `-r` is given, and `-a` changes nothing there.

## Cache & updates

```zsh
bq +update            # update the register if stale
bq +update --force    # force recovery, including a recently corrupted cache
bq +update --offline  # install the bundled catalog as the local cache, offline
```

Releases bundle a sanitized `homebrew/core` and `homebrew/cask` seed catalog. Each load validates the user snapshot, falls back to the seed if it is corrupt, and overlays installed state from local Homebrew roots, including third-party taps; unreadable roots keep the last known state. Live refreshes read installed metadata from local Homebrew and analytics from formulae.brew.sh.

Stale, seed, and incomplete snapshots schedule a detached refresh that waits five minutes, checks system load, and may use the network. `auto-update = false` or `BREWQ_NO_AUTO_REFRESH=1` disables it; `-u` and `+update` still run. If analytics are unavailable during a refresh, previous counts are kept and the scheduler retries later.

`-u` forces a refresh, then queries available data even if the refresh fails or is already running (reported on stderr); the query's result sets the exit code. `--offline` never contacts Homebrew and cannot combine with `--force`. Cache notes print to stderr after rows.

## Configuration

The file is `${XDG_CONFIG_HOME:-~/.config}/brewq/config.toml` unless `BREWQ_CONFIG` overrides it. Keys are root-level long option names, with typo suggestions.

```zsh
bq +config show                    # same as bare `bq +config`; effective values with their source
bq +config defaults > config.toml  # starter TOML
VISUAL="code -w" bq +config edit   # $VISUAL, then $EDITOR; creates a commented-out file if missing
```

Built-in defaults:

```toml
top = "auto" # terminal height; positive integer = fixed cap; 0 = unlimited; -t overrides
sort = "90d"
reverse = false # terminal default; true or -a puts the best row last
columns = ["name", "90d", "trend", "desc"]
installed-columns = ["name", "desc"]
auto-update = true # false, or BREWQ_NO_AUTO_REFRESH=1, skips background updates
max-age = 86400 # seconds
```

Column arrays take concrete field names; `columns` also accepts the config-only `auto`, which resolves to `90d`, `30d`, or `365d` from the top result. `default` is reserved for `-c`. Invalid settings print a diagnostic and fall back field by field. `--help`, `--version`, and `+config defaults` do not load configuration.

## Shell completion

```zsh
source <(brewq +completion zsh)   # after compinit; in a checkout, uv run brewq +completion zsh
```

Tab completes commands, flags, sort fields, comma-separated columns, and package names from the existing user snapshot, even a stale one; without a readable snapshot it offers no package names. Completion never initializes the seed, scans inventory, or refreshes. Regenerate it after moving or recreating its Python environment. Bash and fish are not supported.

## Exit codes & environment

| Code | Meaning |
| --- | --- |
| `0` | Success, including empty results, local-data queries after a refresh failure, and `--help`/`--version` with invalid configuration |
| `1` | Operational failure: unusable cache, failed update; `+config edit` exits `1` on invalid settings and passes through a failing editor's code |
| `2` | Usage error: unknown flags or actions, invalid option values |
| `130` | Interrupted (`Ctrl-C`); no traceback, no partial cache |
| `141` | Closed search pipe (`bq … \| head`); no traceback |

| Variable | Effect |
| --- | --- |
| `BREWQ_CONFIG` | Config file path; otherwise `${XDG_CONFIG_HOME:-~/.config}/brewq/config.toml` |
| `BREWQ_CACHE_DIR` | Cache directory; otherwise `${XDG_CACHE_HOME:-~/.cache}/brewq` |
| `BREWQ_NO_AUTO_REFRESH=1` | Disable background updates; wins over configuration (`1`/`true`/`yes`/`on`; invalid values warn) |
| `NO_COLOR` (nonempty), `TERM=dumb` | Disable ANSI styling on both streams |
| `VISUAL`, `EDITOR` | Editor for `+config edit`, in that order |
| `COLUMNS`, `LINES` | Terminal-size fallback when stdout is not a TTY |

## How `trend` is computed

`trend` is `(90d / 3 + α) / ((365d − 90d) / 275 × 30 + α)`: the recent monthly install rate over the package's own earlier monthly rate. Anchoring "recent" on the 90d window instead of the raw 30d count keeps new-to-tracking packages and late-month spikes from reading as full-strength surges. `α` is a smoothing pseudocount (30 installs, up to 3× for packages with little pre-window history) so tiny baselines don't print hundred-fold multipliers; high-volume counts barely move. `1.0x` means steady; missing history shows `-`.

## Uninstall

```zsh
brewq +setup --remove
brew uninstall brewq   # or: uv tool uninstall brewq
rm -rf "${XDG_CACHE_HOME:-$HOME/.cache}/brewq" "${XDG_CONFIG_HOME:-$HOME/.config}/brewq"   # optional: cache and config
```

## License & development

Original `brewq` code is MIT, Copyright (c) 2026 Ivan Cherniukh ([LICENSE](LICENSE)). The bundled catalog is Homebrew data under BSD-2-Clause, and spell correction adapts Yuki Nishijima's DidYouMean under MIT; both notices are in [NOTICE](NOTICE). Contributor workflow lives in [AGENTS.md](AGENTS.md); from a checkout, `uv run python scripts/random-layout.py [--seed N]` runs the layout lab through the normal search path.

---

Pre-1.0 (`0.x`, [changelog](CHANGELOG.md)) · Homebrew tap or wheel · MIT ([LICENSE](LICENSE), [NOTICE](NOTICE))
