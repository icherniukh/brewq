> Historical snapshot, archived 2026-09-21. This document is not the current contract or roadmap.
> See the repository README, AGENTS.md, and docs/roadmap.md. Paths and issue status below reflect the original context.

# Top-Down Product, UX, and Architecture Review

Date: 2026-06-26

## Verdict

The product boundary is sound: a small, read-only Homebrew query and analytics
CLI is useful, and the cache-only normal path is the right performance shape.
The codebase does not need a rewrite or a larger framework.

It is not release-ready. The main risks are trust failures at state boundaries:
refresh can report success without writing data, malformed local state produces
tracebacks, installed status disappears without ANSI color, and the benchmark
suite can report a passing measurement for the wrong command. These are more
important than adding surface area.

## Method

The review did not use the existing backlog as a checklist. It independently:

- exercised the installed `brewq` shim in TTY and non-TTY contexts
- tested search, list, help, TSV, stale cache, colors, and invalid limits
- injected malformed cache JSON and malformed TOML
- traced cache, ranking, column, rendering, and refresh data flow
- inspected tests and ran the benchmark harness
- compared observed behavior with the product and CLI documents

## Findings

### P0: Refresh success is not a trustworthy state

`cache.refresh()` returns the same `None` result when the cache is fresh, when
another process owns the lock, and when a refresh completes
(`src/brewq/cache.py:71`). `_cmd_refresh()` always follows that call with a
success summary (`src/brewq/cli.py:202`). Analytics errors are swallowed and a
metadata-only cache is written as though refresh fully succeeded
(`src/brewq/cache.py:98`).

Verdict: change. Return and render explicit refresh outcomes. Tracked as
`brewq-isb`.

### P0: Public analytics terminology contradicts the current direction

`Package.popularity_score`, the `POP` column, aliases such as `pop`, `score`,
and `rank`, and help text still expose the composite popularity model
(`src/brewq/model.py:39`, `src/brewq/columns.py:30`,
`src/brewq/options.py:10`). This conflicts with the decision to remove public
popularity and introduce a straightforward trending signal.

Verdict: remove/replace. Existing issue `brewq-4it` is the correct owner.

### P1: Corrupt local state crashes with implementation tracebacks

A malformed `brew-all.json` exits through `json.JSONDecodeError` from
`cache.load_packages()` (`src/brewq/cache.py:117`). A malformed config exits
through `tomllib.TOMLDecodeError` from `config.load()`
(`src/brewq/config.py:49`). Neither path names a recovery action in stable CLI
language.

Observed commands:

```text
BREWQ_CACHE_DIR=<invalid-cache> brewq ripgrep  -> exit 1 + traceback
BREWQ_CONFIG=<invalid-toml> brewq ripgrep      -> exit 1 + traceback
```

Verdict: change. Tracked as `brewq-zij`.

### P1: NO_COLOR removes information, not only color

The installed marker is constructed only inside the colored name branch
(`src/brewq/render.py:187`). With `NO_COLOR=1`, an installed result such as
`node` has no marker in the default table. Non-TTY table output has the same
problem. This contradicts the product promise to mark installed packages.

Verdict: change. Keep the marker plain when ANSI is disabled. Tracked as
`brewq-kgc`.

### P1: Invalid limits create unbounded output

`--top` and `--limit` accept any integer (`src/brewq/cli.py:70` and `:99`).
Negative values bypass the `limit > 0` checks in ranking. `brewq -t -1 -c name
git` printed the complete match set. Explicit zero silently falls back to the
configured search default.

Verdict: change. Validate positive integers at the parser boundary. Tracked as
`brewq-2en`.

### P1: The benchmark suite can pass while timing the wrong workflow

The `cache_status` benchmark still invokes the removed `brewq cache status`
surface (`scripts/benchmark.py:45`). Root search interprets those words as a
query, exits zero, and the benchmark reports zero failures under the label
`cache_status`. Existing benchmark tests validate formatting and selection but
never validate command behavior.

Observed command:

```text
uv run python scripts/benchmark.py --iterations 1 --case cache_status
```

It reported zero failures while measuring a search.

Verdict: change. Tracked as `brewq-cnv`.

### P1: Configuration defaults leak across loads

`config.load()` starts with `dict(DEFAULTS)`, a shallow copy
(`src/brewq/config.py:49`). Applying `BREWQ_CACHE_MAX_AGE` mutates the shared
nested cache dictionary. In one process, loading with `1`, removing the
environment variable, and loading again returns `1` instead of `86400`.

Verdict: change. Tracked as `brewq-wwf`.

### P1: Current tests are fast but not a release gate

The 162-test suite runs in roughly 0.1 seconds because most CLI coverage calls
`main()` with mocked cache data. That is useful unit coverage, but it does not
exercise an installed process, PTY behavior, lock contention, malformed state,
or benchmark command validity. The installed-marker and color regressions show
the right visible-width testing direction.

Verdict: change the verification layer, not the whole test suite. Existing
issues `brewq-1xx.1` and `brewq-1xx.3` own this work.

### P2: Command routing reserves package names

The first token selects a command before root-search parsing
(`src/brewq/cli.py:377`). Packages or queries whose first term is `list`,
`refresh`, `config`, or `random` cannot use the normal root-search shape. This
is a consequence of commandless search, not an immediate release blocker.

Verdict: keep for now; document or revisit only if real package queries collide.

## Existing Work Confirmed

- `brewq-d78`: the fixed top-15 default is not viewport-aware and wrapped rows
  make the visible result count unpredictable.
- `brewq-asn`: normal commands disclose stale data but do not schedule refresh.
- `brewq-1xx.6`: the leading red stale-cache sentence dominates every TTY run.
- `brewq-1xx.5`: deprecated/disabled filtering needs an explicit default and
  exact-match policy.
- `brewq-1xx.4`: renderer width/status logic and CLI orchestration should be
  simplified only while fixing the concrete behaviors above.

## Architecture Verdicts

Keep:

- Python and the current module split
- cache-only normal search/list paths
- one normalized `Package` record
- one column registry shared by table and TSV
- explicit foreground refresh as a supported boundary
- TSV as the sole machine-readable output

Change:

- make refresh outcomes typed and observable
- establish user-facing error boundaries around cache/config parsing
- remove the popularity model instead of layering trending beside it
- centralize visible-width and marker behavior in rendering
- replace mock-only confidence with a small installed CLI/PTY verification suite

Remove:

- obsolete benchmark commands
- temporary color schemes and `--colors` after a default is selected
- compatibility aliases and private paths that no current workflow uses

Do not add:

- a framework rewrite
- permanent theming infrastructure
- another output format
- more commands before the current trust failures are resolved

## Recommended Order

1. Fix refresh outcomes and corrupt-state error boundaries.
2. Add installed-process, PTY, malformed-state, and lock-contention verification.
3. Resolve cache-age presentation and scheduling together.
4. Replace popularity with trending and settle status filtering.
5. Rework default output sizing using measured rendered lines.
6. Simplify touched architecture and then update help/docs.
