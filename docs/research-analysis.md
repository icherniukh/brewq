# Research Analysis

Date: 2026-06-06

## Executive Summary

The exact `bsx` toolset does not appear to exist as a single lightweight CLI today, but there are several adjacent tools. The opportunity is not "Homebrew discovery" broadly. That space already has web directories, TUIs, GUI managers, and at least one popularity-focused CLI.

The viable niche is narrower:

`bsx` is a compact, non-interactive Homebrew query layer. Its core is a richer `brew search`, but it should also absorb the lightweight workflows currently handled by shell aliases: description search (`brew-discover`, `bsd`) and richer installed-package listing (`brew-installed`, `brew-ll`).

That niche is still useful because existing alternatives tend to be one of:

- official but low-context (`brew search`, `brew info --json`)
- browser/web directory
- interactive TUI/GUI
- broader discovery app with categories, random suggestions, and install workflows
- multi-package-manager search tool

`bsx` should stay close to Homebrew query commands: fast, scriptable, compact, no TUI, no install management, no package-manager abstraction.

## What Homebrew Already Provides

Homebrew already exposes most of the raw data needed:

- `brew info --json=v2` includes both formulae and casks.
- `formulae.brew.sh` exposes metadata endpoints for all formulae and all casks.
- Analytics endpoints expose install counts for 30d, 90d, and 365d windows.
- Public analytics are aggregate data, and Homebrew documents that public JSON analytics are available.

Implication: `bsx` should not scrape. It should build on Homebrew JSON and formulae.brew.sh APIs.

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
- category/random/info modes make it broader than `bsx`
- not focused on user-configurable columns as the primary extension model

### Brewse

Observed features:

- interactive TUI browser
- search, view, install, uninstall Homebrew packages
- direct search mode exists

Fit:

- overlaps with terminal-based Homebrew browsing

Gap:

- interactive TUI and package management are outside `bsx` scope
- heavier mental model than `brew search`
- not primarily a scriptable table/JSON command

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

- `brew search bsx` returned `bsc`, not an exact `bsx` formula/cask.
- `brew search fex` returned `fex`.
- `brew search brew-discover` did not show `brew-discover` in the default search here.
- `brew search brewse` did not show `brewse` in the default search here.

External search found unrelated `bsx` packages:

- PyPI has a `bsx` package described as a placeholder Python SDK package for BSO.
- npm has a `bsx` package unrelated to Homebrew search.

Implication:

- A Homebrew formula named `bsx` looks plausible.
- A PyPI distribution named `bsx` is likely unavailable or undesirable.
- If Python packaging matters, consider `brew-bsx`, `homebrew-bsx`, or a source-only install plus Homebrew formula.

## Recommended Lightweight Feature Set

### Core Search

Keep:

- `bsx QUERY`
- `bsx --desc QUERY`
- `--type formula|cask|all`
- `-n`, `--name`
- `-y`, `--year`
- `--limit N`
- `--json`
- `--columns LIST_OR_PROFILE`

Reasoning:

- These options map directly to common decisions: what matched, what kind of package, how popular, how much output, and what fields to display.
- `--columns` prevents flag sprawl by making output customization universal.
- `--desc` replaces the existing `brew-discover='brew search --desc --eval-all'` and `bsd='brew search --desc'` aliases without adding a separate command.

### Installed List

Keep:

- `bsx list`
- `bsx list --type formula|cask|all`
- `bsx list --analytics`
- `bsx list --analytics --fetch`
- `bsx list --columns LIST_OR_PROFILE`
- `bsx list --json`

Reasoning:

- This replaces the current `brew_installed` shell function.
- It reuses the same columns/rendering/config model as search.
- It avoids becoming a package manager because it does not install, uninstall, upgrade, or mutate Homebrew state.

### Config

Keep:

- optional TOML config
- config-backed default columns
- config-backed default metric, type, limit, and format
- `BREWQ_CONFIG`
- `bsx config path`

Reasoning:

- Defaults should be user-owned.
- A config file is lighter than many output flags.
- `config path` is enough for discoverability without becoming a config editor.

### Cache

Keep:

- `bsx cache status`
- `bsx cache refresh`
- `bsx cache refresh --force`
- `bsx cache clear`
- stale-while-revalidate on normal search

Reasoning:

- Cache is central to the product.
- These commands are easy to understand and sufficient for maintenance.

### Columns

First-class built-ins:

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

Profiles:

- `compact`: `name,installs,description`
- `default`: from config, fallback to `name,type,installs,description`
- `full`: `name,type,installs,installed,status,url,description`

Reasoning:

- This is enough to express most useful output without bespoke options.
- More columns can be added without changing the CLI shape.

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

### `--desc`

Search descriptions as well as names.

Why it fits:

- Homebrew already supports description-oriented search behavior.
- It helps when the user knows the concept but not the package name.

Why to be careful:

- can make results noisy
- should be explicit, not default

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

### `--installed`

Filter or mark installed packages.

Why it fits:

- current prototype already marks installed packages

Recommendation:

- mark installed by default if data is cheap
- defer filtering until needed

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

- These move `bsx` away from being a compact search wrapper.
- Existing adjacent tools already cover many of these areas.
- Each adds state, UI, or policy complexity.

## Competitive Conclusion

I did not find an exact existing match for:

- non-interactive Homebrew search replacement
- popularity-aware ranking
- local cache-first speed
- config-backed universal columns
- compact table plus JSON output
- no install management, no TUI, no category browser

There are close competitors around popularity discovery and TUI browsing, especially brew-discover, Brewse, and fex. `bsx` should avoid competing with them broadly. Its differentiation should be restraint: a better `brew search`, not a Homebrew manager.

## Sources

- Homebrew Querying Brew: https://docs.brew.sh/Querying-Brew
- Homebrew Analytics: https://docs.brew.sh/Analytics
- Homebrew Formulae JSON API: https://formulae.brew.sh/docs/api/
- brew-discover article: https://zenn.dev/atani/articles/brew-discover-cli-tool?locale=en
- Brewse PyPI: https://pypi.org/project/brewse/
- fex docs.rs: https://docs.rs/crate/fex/0.2.0
- BrewDB: https://brewdb.vercel.app/
