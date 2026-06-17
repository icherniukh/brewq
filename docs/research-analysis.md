# Research Analysis

Date: 2026-06-06
Current-direction refresh: 2026-06-17

## Executive Summary

The exact `brewq` toolset does not appear to exist as a single lightweight CLI today, but there are several adjacent tools. The opportunity is not "Homebrew discovery" broadly. That space already has web directories, TUIs, GUI managers, and popularity-focused tools.

The viable niche is narrower:

`brewq` is a compact, non-interactive Homebrew query and analytics layer. Its core is a richer `brew search`, and it should also absorb the lightweight workflows currently handled by shell aliases: description search (`brew-discover`, `bsd`) and richer installed-package listing (`brew-installed`, `brew-ll`).

That niche is still useful because existing alternatives tend to be one of:

- official but low-context (`brew search`, `brew info --json`)
- browser/web directory
- interactive TUI/GUI
- broader discovery app with categories, random suggestions, and install workflows
- multi-package-manager search tool

`brewq` should stay close to Homebrew query commands: fast, scriptable, compact, no TUI, no install management, no package-manager abstraction.

## What Homebrew Already Provides

Homebrew already exposes most of the raw data needed:

- `brew info --json=v2` includes both formulae and casks.
- `formulae.brew.sh` exposes metadata endpoints for all formulae and all casks.
- Analytics endpoints expose install counts for 30d, 90d, and 365d windows.
- Public analytics are aggregate data, and Homebrew documents that public JSON analytics are available.

Implication: `brewq` should not scrape. It should build on Homebrew JSON and formulae.brew.sh APIs.

## 2026 Refresh

Homebrew has continued moving toward API-backed metadata and faster internal JSON paths. That supports `brewq`'s cache-first direction: use Homebrew and formulae.brew.sh as authoritative sources, then make repeated local queries faster and more readable than raw `brew search` or `brew info --json`.

Important source facts for the current implementation:

- Formula metadata is available from `https://formulae.brew.sh/api/formula.json`.
- Cask metadata is available from `https://formulae.brew.sh/api/cask.json`.
- Formula analytics should use `install-on-request` so dependency installs do not dominate the trust signal.
- Cask analytics should use `cask-install`.
- Analytics windows are `30d`, `90d`, and `365d`.
- Public analytics are aggregate signals, not a quality guarantee.

The current product implication is sharper than the original `bsx` notes: `brewq` should be cache-first and mostly local after refresh. A normal warm-cache query should not block on live `brew search` / `brew info` unless a later measured design deliberately chooses that tradeoff.

The important gap is presentation and workflow:

- `brew search` finds names, but it does not rank by installs or show rich decision context.
- `brew info --json` is powerful but not ergonomic as a search result UI.
- formulae.brew.sh is a browser experience, not a terminal-first search replacement.

## Existing / Adjacent Tools

### Official Homebrew

Fit:

- canonical source
- exact matching semantics
- installed state and package metadata
- JSON output via `brew info`

Gap:

- no compact popularity-ranked search table
- no configurable search-result columns
- no warm-cache custom index optimized for repeated rich search
- no single compact installed-package list that combines formulae, casks, descriptions, optional analytics, and configurable columns

### formulae.brew.sh / BrewDB-style Web Directories

Fit:

- rich browser discovery
- metadata and analytics display
- useful for manual exploration

Gap:

- not a shell-native replacement for `brew search`
- not ideal for pipes, scripts, aliases, or quick terminal decisions

### brew-discover

Observed features:

- popularity rankings
- category browsing
- random discovery
- enhanced search
- package details
- Homebrew API + analytics data
- Go implementation and tap-based install

Fit:

- overlaps with popularity-aware Homebrew discovery
- validates that popularity ranking is useful

Gap:

- more of a discovery product than a compact `brew search` wrapper
- category/random/info modes make it broader than `brewq`
- not focused on user-configurable columns as the primary extension model

### Brewse

Observed features:

- interactive TUI browser
- search, view, install, uninstall Homebrew packages
- direct search mode exists

Fit:

- overlaps with terminal-based Homebrew browsing

Gap:

- interactive TUI and package management are outside `brewq` scope
- heavier mental model than `brew search`
- not primarily a scriptable table/TSV command

### fex

Observed features:

- universal interactive package search TUI
- supports Homebrew and Linux package managers
- local caching/indexing for Homebrew speed

Fit:

- overlaps with fast package search and Homebrew metadata caching

Gap:

- multi-package-manager abstraction
- interactive TUI orientation
- not specifically a compact Homebrew search-result formatter with configurable columns

### Homebrew GUI / Native Apps

Observed examples include tools positioned as Homebrew managers, package browsers, cask catalogs, and analytics dashboards.

Fit:

- good for browsing, installing, uninstalling, and package management

Gap:

- not terminal-native
- much broader than search result enrichment
- not suitable as a drop-in `brew search` improvement

## Name / Distribution Notes

Local check:

- `brew search brewq` should be rechecked before public release.
- `brew search fex` returned `fex`.
- `brew search brew-discover` did not show `brew-discover` in the default search here.
- `brew search brewse` did not show `brewse` in the default search here.

Implication:

- A Homebrew formula named `brewq` looks plausible but must be verified before release.
- Python packaging can use the existing `brewq` project name if available, but Homebrew distribution is the primary target.
- The historical `bsx` name should remain provenance only.

## Recommended Lightweight Feature Set

### Core Search

Keep:

- `brewq QUERY`
- `brewq -t N QUERY`
- `brewq -s 30d|90d|365d|name QUERY`
- `brewq -l QUERY`
- `brewq -p compact|full QUERY`
- `brewq -c name,30d,url QUERY`
- `brewq --tsv -c name,30d,url QUERY`

Reasoning:

- Default search now covers names, formula aliases, and descriptions. That better matches the query + analytics product goal than preserving Homebrew's exact name-only default.
- `-s` and columns replace old one-off switches like `-n`, `-y`, and `--desc`.
- `-t` is the search cap for top-ranked results; `--limit` remains list-specific.
- `--tsv` is the public machine-readable mode. JSON remains an internal Homebrew/cache format, not a public `brewq` output promise.

### Installed List

Keep:

- `brewq list`
- `brewq list --analytics`
- `brewq list --fetch`
- `brewq list -p compact|full`
- `brewq list -c name,type,version`
- `brewq list --tsv`

Reasoning:

- This replaces the current `brew_installed` shell function.
- It reuses the same columns/rendering/config model as search.
- It avoids becoming a package manager because it does not install, uninstall, upgrade, or mutate Homebrew state.
- Installed rows are formulae and casks together; `type` is part of the default list view.

### Config

Keep:

- optional TOML config
- config-backed default columns
- config-backed default sort, output limit, and cache freshness
- `BREWQ_CONFIG`
- `BREWQ_CACHE_DIR`
- `BREWQ_CACHE_MAX_AGE`
- `NO_COLOR`
- `brewq config path`

Reasoning:

- Defaults should be user-owned.
- A config file is lighter than many output flags.
- `config path` is enough for discoverability without becoming a config editor.
- Config editing commands remain deferred.

### Cache

Keep:

- `brewq cache status`
- `brewq cache refresh`
- `brewq cache refresh --force`
- `brewq cache clear`

Reasoning:

- Cache is central to the product.
- These commands are easy to understand and sufficient for maintenance.
- Warm-cache query speed is now the main release blocker. If the tool shells out on every normal query, it loses the main cache-first advantage.

### Columns

First-class built-ins:

- `name`
- `type`
- `version`
- `installs`
- `installs_30d`
- `installs_90d`
- `installs_365d`
- `popularity`
- `binaries`
- `description`
- `installed`
- `status`
- `url`

Profiles:

- search `compact`: `name,installs_30d,description`
- search `default`: from config, fallback to `name,installs,description`
- search `full`: `name,type,version,installs_30d,installs_90d,installs_365d,installed,status,description`
- list `compact`: `name,type,description`
- list `default`: from config, fallback to `name,type,version,description`
- list `full`: `name,type,version,installs_30d,installed,status,description`

Reasoning:

- This is enough to express most useful output without bespoke options.
- More columns can be added without changing the CLI shape.

## Local Lab Command

`brewq random` is allowed for local layout testing and inspiration. It should:

- choose from a fixed query list
- vary sort, top count, preset, and explicit columns
- print the generated `brewq ...` command to stderr
- run the normal search/rank/render path

It should not become category browsing, recommendations, or a public product promise.

## Logical Additions That Stay Lightweight

These are logical, but should be added only if the core is clean.

### `--explain`

Show why ranking/matching happened:

- matched name vs description
- install metric used
- cache age

Why it fits:

- useful for trust/debugging
- non-interactive
- no new mode

Why to defer:

- requires preserving match metadata

### Search scope controls

Default search already covers names, aliases, and descriptions.

Why controls may fit later:

- measured output may show noisy description matches
- scripts may want exact name-only behavior
- debugging ranking is easier when search scope is explicit

Why to defer:

- the current surface is intentionally smaller without `--desc`, `--desc-only`, or `--name-only`
- adding controls before measuring output risks preserving prototype clutter

### `--open`

Open the selected or first result homepage/formula page.

Why it fits:

- common terminal-to-browser bridge

Why to defer:

- selection semantics get tricky
- not needed for first release

### `--exact`

Restrict to exact token/name match.

Why it fits:

- useful for scripts and package verification

Why to defer:

- matching semantics should be settled after cache-vs-brew-search decision

### Installed-state enhancements

The current search surface has `-l` / `--installed` for installed-only filtering, and selected columns can expose installed state.

Possible later additions:

- clearer installed markers in compact output
- installed-state ranking boosts
- installed-list leaves mode

Why to defer:

- installed metadata should remain read-only
- leaves/dependency behavior can pull the tool toward package-management workflows

## Features To Avoid

Avoid for first release:

- install/uninstall commands
- TUI mode
- category browsing
- random package discovery
- dependency tree views
- vulnerability/security scoring
- GitHub star ranking
- multi-package-manager support
- package notes/bookmarks
- bulk selection workflows
- config editing commands

Reasoning:

- These move `brewq` away from being a compact query and analytics wrapper.
- Existing adjacent tools already cover many of these areas.
- Each adds state, UI, or policy complexity.

## Competitive Conclusion

I did not find an exact existing match for:

- non-interactive Homebrew search replacement
- popularity-aware ranking
- local cache-first speed
- config-backed universal columns
- compact table plus TSV output
- no install management, no TUI, no category browser

There are close competitors around popularity discovery and TUI browsing, especially brew-discover, Brewse, and fex. `brewq` should avoid competing with them broadly. Its differentiation should be restraint: a better `brew search`, not a Homebrew manager.

## Sources

- Homebrew Querying Brew: https://docs.brew.sh/Querying-Brew
- Homebrew Analytics: https://docs.brew.sh/Analytics
- Homebrew Formulae JSON API: https://formulae.brew.sh/docs/api/
- brew-discover article: https://zenn.dev/atani/articles/brew-discover-cli-tool?locale=en
- Brewse PyPI: https://pypi.org/project/brewse/
- fex docs.rs: https://docs.rs/crate/fex/0.2.0
- BrewDB: https://brewdb.vercel.app/
