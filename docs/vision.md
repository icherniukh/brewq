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
brewq --desc terminal multiplexer
brewq --top 10 json
brewq list
brewq list --analytics
brewq --columns compact rust
brewq --json rust
```

Homebrew aliases should be supported as a convenience layer:

```bash
brew q ripgrep
brew qd terminal multiplexer
brew ql --analytics
```

Those aliases should point to `brewq`; they should not force the tool to become a full wrapper around `brew`.

## Search Semantics

Homebrew default behavior, verified from `brew search --help`, is:

- default `brew search TEXT` performs substring search of cask tokens and formula names
- `brew search --desc TEXT` searches formula descriptions and cask names/descriptions

`brewq` should be query-and-analytics-first, not a byte-for-byte clone of `brew search`.

Default `brewq QUERY` should match Homebrew's default search scope: cask tokens and formula names. Description search should stay one explicit flag away via `--desc`, because it is useful but can be noisy.

Compatibility should still be available:

```bash
brewq ripgrep
brewq --desc multiplexer
```

Search ranking should combine:

- match source: exact/name/token matches above weaker matches
- install popularity: default 30-day installs
- package state: disabled/deprecated packages should be visibly marked and probably ranked lower

## Popularity And Top-N

The central discovery operation is:

```bash
brewq --top 10 QUERY
```

`--top N` should mean "show the top N most relevant, most installed results." It is not merely a row limit. It should apply after matching, scoring, and analytics-aware ranking.

`--limit N` may still exist as a dumb output cap, but `--top N` is the analytics-backed query feature.

Initial metric:

- 30-day installs by default
- 365-day installs via `--year`

Potential future metric:

- trend score based on 7d/30d/365d dynamics, if the data source supports it cleanly

Trend score is not MVP. It should not block the first release.

## Output Model

Output customization should be universal, not a pile of bespoke flags.

Columns are the extension point:

```bash
brewq --columns compact QUERY
brewq --columns default QUERY
brewq --columns full QUERY
brewq --columns name,type,installs,url QUERY
```

Built-in column presets:

- `compact`: small terminal view, likely `name,installs,description`
- `default`: normal discovery view, from config
- `full`: wide inspection view, likely `name,type,version,installs,installed,status,url,description`

The exact default columns belong in config:

```toml
[output]
columns = ["name", "version", "installs", "description"]
```

Script-friendly output is first-class:

```bash
brewq --json QUERY
brewq list --json
```

JSON should come from the same normalized records as table output. It should not be an afterthought bolted onto terminal rendering.

## Installed Package Listing

`brewq list` should absorb the useful parts of the current `brew_installed` function:

- list installed formulae and casks together
- show descriptions
- optionally show analytics
- support the same columns/presets as search
- support JSON
- avoid network fetches by default

Examples:

```bash
brewq list
brewq list --analytics
brewq list --columns compact
brewq list --columns name,type,version,description
```

This is still query/read-only behavior. It should not grow into uninstall, upgrade, services, cleanup, or Brewfile management.

## Cache Strategy

Cache is part of the product, not hidden plumbing.

MVP cache behavior:

- warm-cache queries should be fast
- normal search should not require network access
- cache refresh should be atomic and lock-protected
- stale cache should be usable while a refresh happens
- cache commands should be simple: `status`, `refresh`, `clear`

Potential cache strategies:

- `manual`: only refresh on explicit `brewq cache refresh`
- `stale-while-revalidate`: use stale cache and refresh in background
- `blocking-when-missing`: first run waits for a complete cache if no cache exists
- `live-fallback`: first run uses slower live Homebrew data while cache builds

The default should optimize perceived responsiveness. The exact default can be decided after measuring cold-cache behavior.

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
- fast JSON output for scripting
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
- `brewq --top N QUERY` surfaces the most trusted/popular candidates quickly.
- `brewq list` replaces the existing installed-package shell function.
- default columns are useful immediately but easy to change in config.
- JSON output is clean enough for scripts.
- warm-cache search feels instant.
- first release is useful before any semantic/vector-search work.
