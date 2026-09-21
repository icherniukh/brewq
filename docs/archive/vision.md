> Historical snapshot, archived 2026-09-21. This document is not the current contract or roadmap.
> See the repository README, AGENTS.md, and docs/roadmap.md. Paths and issue status below reflect the original context.

# brewq Vision

`brewq` is a fast, read-only Homebrew query and analytics tool.

It is not a package manager, not a TUI, and not a replacement for `brew install`, `brew upgrade`, or `brew services`. It exists to answer a narrower question very well:

> "What does Homebrew know about this package/query, and what should I trust?"

The core product idea is that Homebrew metadata plus install analytics should be easy to query. Install count is a useful signal for trust, quality, and maintenance probability. Popularity is not truth, but when choosing between similar packages, it is a practical ranking signal. `brewq` should make that signal visible at the exact moment the user searches, compares, or reviews installed packages.

## Product Shape

`brewq` should cover three read-only workflows:

1. Query packages by name and description.
2. Compare results by install analytics and useful metadata.
3. Inspect installed formulae and casks with richer, configurable columns.

The daily interface should feel compact:

```bash
brewq ripgrep
brewq terminal multiplexer
brewq -t 10 json
brewq list
brewq list --analytics
brewq -u rust
brewq --tsv rust
```

Homebrew aliases should be supported as a convenience layer:

```bash
brew q ripgrep
brew qd terminal multiplexer
brew ql --analytics
```

Those aliases should point to `brewq`; they should not force the tool to become a full wrapper around `brew`.

## Search Semantics

Homebrew baseline behavior, verified from `brew search --help`, is:

- default `brew search TEXT` performs substring search of cask tokens and formula names
- `brew search --desc TEXT` searches formula descriptions and cask names/descriptions

`brewq` should be query-and-analytics-first, not a byte-for-byte clone of `brew search`.

Default `brewq QUERY` should cover names, formula aliases, and descriptions, because the product goal is useful query and comparison rather than strict Homebrew compatibility. If this proves noisy, add a search-scope control later from measured output, not as prototype flag preservation.

Examples:

```bash
brewq ripgrep
brewq multiplexer
```

Current search ranking combines:

- exact package or alias matches first
- install volume across the remaining matches, using the selected analytics window
- package state: disabled/deprecated packages are hidden from capped results unless `--all` is given; otherwise they are visibly marked and ranked after active packages

## Popularity And Top-N

The central discovery operation is:

```bash
brewq -t 10 QUERY
```

`-t N` should mean "show the top N highest-ranked results." It applies after matching, scoring, and analytics-aware ranking, ranked by whatever sort field is in effect.

`--limit N` remains list-specific output capping.

Sort fields:

- `90d` by default — raw `installs_90d`, the most trustworthy default trust
  signal for a query result list (see brewq-253)
- `30d`, `365d` when requested — raw install counts, other windows
- `trending` (a 90d-anchored installation rate as a multiplier of a package's
  own 365d historical baseline, e.g. `4.1x`; pseudocount-smoothed, with the
  pseudocount itself scaling up for packages with little pre-90d history, so
  neither a handful of installs nor a new-to-tracking package can read as a
  wild swing — see brewq-4o0) remains available as an explicit, demoted signal
- `name` for alphabetical output

Superseded: this section originally deferred a trend metric past MVP and kept raw
install counts as the default signal. That direction changed — see brewq-4it —
because raw install counts alone over- or under-represent packages that are
simply old or new rather than currently relevant.

Superseded: the first `trending` implementation expressed growth as a signed
percent (`+25%`) clamped to `±300%`. That clamp tied dozens of unrelated
packages at an identical ceiling and hid brand-new packages entirely (no
history meant no signal). Replaced — see brewq-sbe — with a pseudocount-smoothed
multiplier that has no hard ceiling and naturally damps low-volume noise
instead of capping it after the fact.

Superseded: trending (recent-vs-historical-baseline ratio) then became the
default ranking signal — see brewq-4it/brewq-sbe. That reversed — see
brewq-253 — because a self-relative growth ratio is a new-package artifact
magnet: a package recently added to Homebrew analytics tracking can show a
~250x multiplier on a handful of installs, ranking it ahead of packages with
genuinely large, trustworthy install bases. Raw 90d install volume is the
default again; trending remains available as a demoted, opt-in signal.

Superseded: brewq-253 demoted trending from the default sort but didn't fix
the underlying multiplier — the TREND column itself still showed the same
150-270x new-package artifacts. brewq-4o0 recalibrated the formula: the
"recent" rate anchors on the 90d window instead of the raw 30d snapshot (so a
burst concentrated in the last 30 days is dampened whether the package is new
or established), and the pseudocount scales up for packages with little
pre-90d history instead of staying fixed, pulling them toward neutral in
proportion to how little history they have rather than collapsing them flat.

## Output Model

Output customization should be universal, not a pile of bespoke flags.

Columns are the extension point:

```bash
brewq -u QUERY          # add the homepage URL column
brewq -v QUERY          # show every package field
brewq -c name,type,30d,url QUERY
```

There are no named presets. Two shortcuts cover the common reach-fors: `-u`
adds the `url` column to the active set, and `-v` expands to the full field
set. Anything more specific is an explicit `-c` list.

The exact default columns belong in config:

```toml
[output]
columns = ["name", "version", "installs", "description"]

[list]
columns = ["name", "type", "version", "description"]
```

Script-friendly output is first-class:

```bash
brewq --tsv QUERY
brewq list --tsv
```

TSV should come from the same normalized records as table output. It should not be an afterthought bolted onto terminal rendering.

## Installed Package Listing

`brewq list` should absorb the useful parts of the current `brew_installed` function:

- list installed formulae and casks together
- show descriptions
- optionally show analytics
- support the same column system, with list-shaped defaults
- support TSV
- avoid network fetches by default

Examples:

```bash
brewq list
brewq list --analytics
brewq list -u
brewq list -c name,type,version,description
```

This is still query/read-only behavior. It should not grow into uninstall, upgrade, services, cleanup, or Brewfile management.

## Cache Strategy

Cache is part of the product, not hidden plumbing.

MVP cache behavior:

- warm-cache queries should be fast
- normal search should not require network access
- cache refresh should be atomic and lock-protected
- stale cache should remain usable without blocking normal commands
- normal output should concisely disclose cache age
- releases should bundle a seed cache for non-blocking first use
- seed-backed queries should overlay local installed state before rendering
- stale cache should schedule one detached refresh after rendering
- background refresh should wait briefly and run only under acceptable load
- manual `brewq refresh` and `brewq -r QUERY` should be optional recovery controls

Current cache lifecycle:

- `bundled-seed`: release-time metadata and analytics make an empty user cache usable
- `local-overlay`: Cellar/Caskroom metadata supplies installed names and versions on first use
- `stale-while-refresh`: stale results render before one delayed worker is scheduled
- `blocking-when-requested`: optional `brewq -r QUERY` refreshes before rendering

The default stays quick. Fresh commands do not spawn work; seed-backed and stale
commands only pay the small detached-worker scheduling cost after rendering.

## Future Direction: Smarter Search

Semantic search is a separate direction.

Possible future design:

- collect package descriptions and project URLs
- optionally fetch homepage/README/project metadata
- generate local embeddings
- build a local vector index
- answer capability-style queries, not just text queries

Example:

```bash
brewq "fast json processor with streaming support"
```

This should not be part of the first release. It changes the tool from "fast metadata query" into "local semantic query." That may be valuable, but it needs a separate design pass and different performance/storage constraints.

## Performance Vision

Stage 1 should prioritize correct shape, clean data boundaries, and fast iteration in an easy-to-move language.

Stage 2 should be unreasonably performance-focused.

Performance goals for Stage 2:

- near-instant warm-cache search
- no repeated linear joins during cache build
- indexed local search data
- stable renderer with no visible layout lag
- fast TSV output for scripting
- cheap installed-list queries

If Python becomes the bottleneck after the product shape is right, a rewrite in Rust, Go, or another compiled language should be considered. The rewrite decision should be made from measured hotspots, not from aesthetic preference.

Stage 1 should still design the architecture so a rewrite is possible:

- clear cache schema
- normalized records
- renderer separated from search/ranking
- tests built around fixtures
- CLI contract documented before optimization

## Non-Goals

Do not build:

- install/uninstall/upgrade
- TUI
- GUI
- service management
- Brewfile management
- multi-package-manager support
- random package browser
- category dashboard
- security scanner

These can be useful tools, but they are not `brewq`.

Exception: `brewq random` may exist as a local lab command for testing output layouts and sparking query ideas. It should print the generated command and run normal search/output paths. It should not become category browsing, recommendations, or a public product promise.

## Private Competitive Context

Keep this section isolated. Do not publish it in public-facing README or release material.

The nearby tools are not the same product, but they define the competitive pressure:

- `brew-discover` is closer on popularity-driven discovery, categories, and random exploration.
- Brewse is closer on interactive Homebrew browsing and package-management actions.
- fex is closer on broad package search and interactive package-manager abstraction.
- GUI tools such as BrewLens, Tappie, and Bold Brew cover visual browsing/management.

`brewq` should not chase those products directly.

The defensible lane is:

- read-only
- shell-native
- query-first
- popularity-aware
- config-column-driven
- fast cache-first output
- useful as standalone command and through `brew alias`

If `brewq` starts adding category browsing, random discovery, install/uninstall, or TUI behavior, it moves into crowded territory and loses the simplicity advantage.

## Success Criteria

- `brewq QUERY` helps query and compare packages without opening formula pages.
- `brewq -t N QUERY` surfaces the most trusted/popular candidates quickly.
- `brewq list` replaces the existing installed-package shell function.
- default columns are useful immediately but easy to change in config.
- TSV output is clean enough for scripts.
- warm-cache search feels instant.
- first release is useful before any semantic/vector-search work.
