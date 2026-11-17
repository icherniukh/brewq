# brewq

`brewq` is a read-only Homebrew query and analytics tool: find packages, compare
install counts, and inspect installed formulae and casks. It does not install,
upgrade, uninstall, manage services, or manage Brewfiles.

## Install and run

Requires Python 3.12+ and Homebrew for local inventory and refresh operations.

```sh
uv tool install <wheel>
brewq +setup
brewq ripgrep
bq ripgrep
```

`uv tool install` installs `brewq` only. `brewq +setup` links `bq` beside it when
that name is free in the command directory and is not a shell alias or function.
An existing foreign `bq` is left unchanged. `brq` is not created. Remove the
shortcut and package with:

```sh
brewq +setup --remove
uv tool uninstall brewq
```

That leaves cache and config in place. To remove those too:

```sh
rm -rf "${XDG_CACHE_HOME:-$HOME/.cache}/brewq" "${XDG_CONFIG_HOME:-$HOME/.config}/brewq"
```

Use `uv run brewq` in a checkout to run its source rather than an older
user-level installation. After verifying an updated build, `uv tool install
--force <wheel>` replaces the installed copy, then run `brewq +setup` again.
Compare `brewq --version` with `uv run brewq --version` when diagnosing drift.

### Zsh completion

After zsh's completion system is initialized (`autoload -Uz compinit; compinit`,
if your shell setup does not already do this), load completion for both commands:

```zsh
source <(brewq +completion zsh)
```

Put that line after completion initialization in your zsh configuration to keep
it enabled. For a checkout, use `source <(uv run brewq +completion zsh)` instead.
Tab completes commands, flags, sort fields, comma-separated columns, and cached
formula/cask names. Package suggestions use the existing user cache even when
stale; a missing, unreadable, or invalid cache yields no package suggestions.
Completion never initializes the seed, scans installed packages, refreshes data,
or schedules work. It binds to the generating Python environment, so regenerate
it after moving or recreating that environment. Bash/fish and `brew` completion
integration are not provided.

## Search and output

```sh
brewq                              # top overall; fits the terminal height
brewq -s trend                     # top rising packages
brewq terminal multiplexer
brewq -t 10 json
brewq -i -t 10 grep
brewq -s 365d rust
brewq -c name,90d,url ripgrep
brewq --tsv -c name,90d,url ripgrep
```

`brewq --help` shows the common search path. `brewq --full-help` adds the full
column reference plus concise trending and cache behavior. `-V` / `--version`
prints the version.

Search matches names, formula aliases, and descriptions. Flags may appear
before, between, or after query terms. A `+action` is recognized only as the
first token; bare words are always query terms. All query terms must match;
name normalization applies. For homebrew/core and homebrew/cask, results are a
superset of `brew search`: its substring and spell-correction (DidYouMean) matches
are reproduced for formulae and casks, and `/regex/` queries are supported. Packages
from third-party taps are not in the catalog, so `brew search` can list names brewq
cannot. An omitted query or an explicitly empty query (`bq ""`) selects the
whole catalog before filters, sorting, and caps; `-i` still selects installed
packages. `brew search` exits 1 when nothing matches; brewq exits 0.
The default sort is raw 90-day install volume. Exact name/alias matches precede
all other matches under every sort, regardless of status. Other disabled/deprecated
results rank last and are never filtered out. `-s name` sorts alphabetically
within those status groups after exact matches.

| Search option | Current behavior |
| --- | --- |
| `-s`, `--sort FIELD` | `90d` (built-in default), `30d`, `365d`, `trend`, or `name` |
| `-R`, `--reverse` | Reverse the chosen order after the cap, so the best row is last |
| `-t`, `--top N` | Positive result cap; overrides configuration |
| `-i`, `--installed` | Show installed packages, optionally filtered by query |
| `-u`, `--update` | Force a register refresh, then query; use local data if refresh fails |
| `-a`, `--all` | Remove the cap and put the best row last on a TTY |

For terminal tables, cap precedence is explicit `-t N`, then `-a` (unlimited),
then configured `top`. The default `top = "auto"` fits the terminal height:
`max(1, rows - 8)` records. Eight lines cover the leading blank, header, rule,
trailing blank, `showing N of M` notice, cache note, typed command, and next prompt.
When the layout falls back to vertical records, auto sizing counts each shown
field's wrapped lines and the separator after each record, reserving four lines
for notices, the command, and the prompt. It keeps at least one record, which can
still overflow a very short terminal. Fixed configured counts and explicit `-t`
are never reduced for vertical output. Wrapped notices remain future work.
Both height and width come from stdout's terminal, ignoring stale `LINES`/`COLUMNS`;
those variables are fallbacks only without a TTY.

A cap that hides rows reports `showing N of M; -a for all, -t N for a count` on
stderr; M counts every match, inactive ones included. Pipes and TSV ignore
configured caps and reverse: they are uncapped and best-first unless `-t` or `-R`
is explicitly given. `-a` does not change their ordering. Machine-readable stdout
stays clean.

These output options work for search, including `-i`:

| Output option | Current behavior |
| --- | --- |
| `-c`, `--columns COLS` | Exact ordered fields; `default` or `all` |
| `--tsv` | Selected columns as raw tab-separated rows, without a header |
| `--no-color` | Suppress ANSI styling on stdout and stderr |

Fields have one exact name shared by `-c`, `-s` (for sortable fields), and
configuration: `name`, `type`, `ver`, `30d`, `90d`, `365d`, `trend`, `bin`, `url`,
`desc`, `inst`, `status`. Each matches its table header lowercased. `inst` and
`status` are TSV-only; selecting them in table mode fails with guidance to use
`--tsv`. Search tables show installed state as the name's ✔ marker; `-i` omits
it because every result is installed. Package status appears as a description
prefix. Typos suggest exact names without automatically resolving them.

`-c` always specifies the exact ordered list. `default` expands the current
view's configured columns, and `all` expands every field available in the output
mode (including `inst` and `status` with `--tsv`). Duplicates keep their first
occurrence: `url,default` puts URL first; `default,name` leaves the default
layout unchanged. `default` and `all` are reserved words, not field names.

```sh
brewq --full-help                    # field reference; no cache needed
brewq ripgrep -c default,ver,bin      # configured view, then version and binaries
brewq rust -c name,90d,url,desc       # exact selection without trend
brewq rust -c url,default            # URL first, then the configured view
brewq -i -c default,90d,trend        # extend the installed-package view
brewq ripgrep -c all --tsv           # every field, with raw values
brewq ripgrep -c name,ver,90d        # exact selection and order
```

Signed `+x`/`-x` tokens are rejected with the equivalent full list: for example,
`-c +url,-trend` says `use -c name,90d,url,desc` with the built-in search layout.
To omit a field, write the desired list. `default` and `all` can change between
releases; scripts should list concrete fields. The same controls work with `-i`.

Cask binaries come from declared artifacts; formula binaries require local
installed data.

Ordinary search defaults to `name,90d,trend,desc`. Installed-only
search (`-i`) uses `installed-columns`, defaulting to `name,desc`;
explicit `-c` overrides that layout. Names use their content width: descriptions
shrink to about 20 display columns before names are clipped, with package
basenames retained where possible. Widths account for wide CJK characters and
combining marks. Long URL and binary cells can be clipped; short metadata such
as type, version, and counts keeps its full displayed value. Layouts that cannot
fit these minimums (including `-c all` on narrower terminals) use labeled vertical
records, showing installed state once and skipping empty fields per record.

Tables omit columns whose shown values are all blank or `-`, even with explicit
`-c`; NAME is never omitted. Only fields named explicitly in `-c` receive a note
on stderr when hidden, such as `brewq: no bin values in these results; column hidden`.
`default` and `all` hide empty columns silently; `-c default,bin` notes only BIN.
Human-readable URLs omit a leading `https://` and a root-path trailing `/`
(`jsonnet.org/` becomes `jsonnet.org`); `http://` and nonempty paths remain visible.
TSV always retains the selected columns and full URLs and values.
`trend` is a smoothed recent-to-historical
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
theme and are enabled independently for each stream only when it is a TTY.
A nonempty `NO_COLOR`, `TERM=dumb`, or `--no-color` suppresses all ANSI styling
on stdout and stderr, including cache footers and usage errors. Installed and
trend markers (`✔` outside `-i`, `↑↑`) remain visible without color. Pipes and TSV stay
ANSI-free.

## Installed packages

```sh
brewq -i
brewq -i grep
brewq -i -s name
brewq -i -c name,type,ver,90d,desc
brewq -i -t 10
brewq -i --tsv -c name,type,ver
```

`-i [query]` is the only installed view. The default sort is the search sort
(90-day install volume unless configured); `-i -s name` sorts alphabetically across formulae
and casks, with deprecated/disabled rows last. Configured `top`, explicit caps,
`--all`, and reverse use the same policies as search; a cap reports
`showing N of M` on stderr. Select cached
analytics through the same `-c` column interface used by search; this never
fetches analytics on demand. VER displays the installed version for installed
rows; the catalog's available version remains separate internally.

## Cache and recovery

The cache footer uses subdued neutral text on a color terminal. Age, incomplete
analytics, and background update scheduling remain visible without red freshness accents.

Releases bundle a seed catalog, with builder-local home paths and installed
state removed during seed generation. Loads validate the user snapshot before using it,
fall back to the seed after corruption, and reconcile installed state from local
Homebrew roots. A successful empty inventory clears stale installed markers;
missing or unreadable roots preserve the last known state. Stale, seed, and
incomplete snapshots can start a detached background update after a five-minute
delay, and only when the system is not busy. That process is on by default and
can use the network. Set `auto-update = false` or
`BREWQ_NO_AUTO_REFRESH=1` to render the same rows without starting it or writing
scheduler state. The environment value wins over configuration; an invalid value
warns and leaves the configured setting. `brewq +update` still runs in the
foreground when you ask for it. Cache information goes to stderr after rows are
flushed.

Snapshots record analytics completeness independently of file age. If metadata
refresh succeeds while analytics is unavailable, brewq retains usable counts
from the previous snapshot, marks the new snapshot for repair, and retries after
the scheduler cooldown. JSON, pickle, and scheduler state use atomic replacement.

```sh
brewq +update            # update the register if stale
brewq +update --force    # force recovery, including a recently corrupted cache
brewq +update --offline  # install the bundled catalog as the local cache, offline
brewq -u ripgrep        # update the register, then search
brewq -a -i             # all installed matches, best row last on a TTY
brewq +config           # print the configuration file path
```

`+update --offline` replaces the cache with the bundled catalog without contacting
Homebrew. It cannot be combined with `--force`.

`-u` / `--update` forces the same foreground refresh used by `+update --force`,
then runs the query (including `-i`). If metadata refresh fails, brewq reports
the failure on stderr, preserves the previous snapshot, and queries that data.
The query exits successfully if local data can be loaded; refresh failure alone
does not make it fail. Without a usable user snapshot, the bundled seed is the
offline fallback. If neither local source is usable and bootstrap also fails,
the query fails. An analytics-only failure retains previous usable counts in a
new metadata snapshot, reports incomplete analytics, and still queries it.
Normal queries need no network; use `BREWQ_NO_AUTO_REFRESH=1` to suppress
background refresh attempts while offline. `-u` explicitly requests a refresh
even with background updates disabled.

## Configuration

Configuration lives at `${XDG_CONFIG_HOME:-~/.config}/brewq/config.toml`, unless
`BREWQ_CONFIG` overrides it. `brewq +config` prints this path without loading
operational configuration. Built-in defaults:

```toml
sort = "90d"
reverse = false # terminal default; true or -a puts the best row last
top = "auto" # terminal height; positive integer = fixed cap; 0 = unlimited; -t overrides
columns = ["name", "90d", "trend", "desc"]
installed-columns = ["name", "desc"]
max-age = 86400 # seconds
auto-update = true # false, or BREWQ_NO_AUTO_REFRESH=1, skips background updates
```

`BREWQ_CACHE_DIR` overrides the cache directory, otherwise
`${XDG_CACHE_HOME:-~/.cache}/brewq` is used. Set `max-age` in configuration to
control cache age in seconds. There are no preset-management commands or named
column presets.

The `auto` pseudo-column in search output configuration selects an available raw
metric from the top result, preferring 90d, then 30d, then 365d. It is rejected
in `installed-columns` and explicit `-c`; prefer explicit metric columns in scripts.

Config keys are root-level long option names (including `reverse`). Typos offer
“did you mean” suggestions; only exact names are accepted. Column arrays contain
concrete names, with `auto` as the search-only exception; `default` and `all`
are CLI selection words.

Invalid keys, types, ranges, sort names, and columns emit a concise
stderr diagnostic and fall back field-by-field. Help, version, and `+config` do
not load operational configuration.

## License

Original brewq code is MIT, Copyright (c) 2026 Ivan Cherniukh. The bundled
catalog is Homebrew data under the BSD-2-Clause license, and spell correction
adapts Yuki Nishijima's DidYouMean under MIT. Both notices are in `NOTICE`.

## Known limits

- Explicit result counts and a single oversized vertical record can exceed the
  terminal height. `-R` puts the best row last when you want it in view.
- The catalog is Homebrew core and cask data. Third-party taps are absent.
- `bq` exists only after `brewq +setup`, and only when that name is free.
- Colors follow the terminal theme; nonempty `NO_COLOR`, `TERM=dumb`, and
  `--no-color` disable styling on both streams.
- There is no install, upgrade, uninstall, or service command.

Contributor workflow lives in [AGENTS.md](AGENTS.md). The layout lab runs with
`uv run python scripts/random-layout.py [--seed N]` from a checkout, using the
same layouts and normal search path.
