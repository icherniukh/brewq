> Historical snapshot, archived 2026-09-21. This document is not the current contract or roadmap.
> See the repository README, AGENTS.md, and docs/roadmap.md. Paths and issue status below reflect the original context.

# Brainstorm / Research Review

Date: 2026-06-06

## Positioning

This should be a compact Homebrew query tool, not a Homebrew manager.

The strongest shape is:

- richer default search
- description search
- installed package listing
- local cache and analytics
- configurable columns
- table/JSON output

The wrong shape is:

- TUI
- GUI
- install/uninstall/upgrade
- package-manager abstraction
- category browser
- dashboard

The market already has many managers and browsers. The gap is a fast shell-native query layer.

## Existing Landscape

Homebrew already exposes the data:

- `brew info --json=v2` covers formulae and casks.
- `brew info --json=v2 --installed` covers installed formulae and casks.
- formulae.brew.sh exposes formula/cask JSON.
- formulae.brew.sh exposes analytics for formula installs, install-on-request, and cask installs across 30d, 90d, and 365d windows.

Adjacent tools:

- `brew-discover`: popularity/category/random discovery tool, broader than this.
- Brewse: interactive TUI for searching, viewing, installing, and uninstalling.
- fex: universal interactive package search TUI with Homebrew support.
- Tappie, Bold Brew, Taphouse, BrewLens, Brewery, brew-browser: GUI/TUI/Homebrew-manager space.

Conclusion:

Do not compete as a manager. Compete as "better query output for Homebrew."

## Product Boundary

### Keep

- `QUERY`: default name search.
- `--desc QUERY`: description search, replacing local `brew-discover` / `bsd`.
- `list`: installed package list, replacing local `brew-installed` / `brew-ll`.
- `cache status|refresh|clear`: enough cache control to make the cache trustworthy.
- `--columns`: universal output customization.
- config-backed default columns.
- `--json`: scriptable output.
- `--type formula|cask|all`.
- `--limit`.
- `-n` / `--name`.
- `-y` / `--year`.

### Consider After MVP

- `info NAME`: cache-backed compact detail view.
- `list --leaves`: installed formulae that are user-facing leaves.
- `list --outdated`: only if it can use cheap Homebrew data without becoming a manager.
- `--explain`: show cache age, match type, and ranking metric.
- `--exact`: useful for scripts.
- `--open`: open homepage or formula page for one selected result.

### Avoid

- install/uninstall/upgrade commands.
- service management.
- security scanning.
- Brewfile import/export.
- bookmarks.
- category browsing as a core mode.
- random package discovery.
- dashboard.
- TUI/fzf embedded UI.
- multi-package-manager support.

## Interface Recommendation

Use this as the first serious interface:

```bash
brewq ripgrep
brewq --desc "terminal multiplexer"
brewq --type cask browser
brewq -n ripgrep
brewq -y ripgrep
brewq --columns name,type,installs,url ripgrep
brewq --json ripgrep

brewq list
brewq list --type formula
brewq list --columns name,type,version,description
brewq list --analytics
brewq list --json

brewq cache status
brewq cache refresh
brewq cache clear
brewq config path
```

If the name stays `bsx`, substitute `bsx`.

The command surface stays small because columns absorb output customization.

## Column Model

Columns are the key extensibility point.

Initial columns:

- `name`
- `type`
- `version`
- `description`
- `installed`
- `status`
- `url`
- `license`
- `tap`
- `installs`
- `installs_30d`
- `installs_90d`
- `installs_365d`

Profiles:

- `default`: from config
- `compact`: `name,installs,description`
- `full`: `name,type,version,installs,installed,status,url,description`
- `list`: `name,type,version,description`

Rules:

- config owns defaults
- `--columns` overrides config per invocation
- unknown columns fail clearly
- JSON output should use the same selected columns by default

## Naming Review

### Recommendation

Best candidate: `brewq`

Why:

- communicates "brew query"
- short enough for repeated terminal use
- less opaque than `bsx`
- broad enough for search, desc, list, and info
- does not imply install/manage behavior

Risks:

- Web search shows unrelated beer-industry products named BrewQ.
- `brew search brewq` returned nearby names but no exact match in this environment.
- Needs final GitHub/PyPI/npm/domain check before release.

### Strong Alternatives

`brewfind`

- Very clear.
- Slightly too search-specific now that installed-list is in scope.
- `brew search brewfind` did not show an exact match here.

`brewscope`

- Good for query/inspect/list.
- Slightly abstract.
- `brew search brewscope` did not show an exact match here.

`brewview`

- Clear enough for read-only browsing/listing.
- Risks sounding like GUI/TUI.
- `brew search brewview` did not show an exact match here.

`bsx`

- Already exists locally.
- Short and distinctive.
- Opaque; does not tell new users what it does.
- PyPI/npm have unrelated `bsx` names, so distribution outside Homebrew is awkward.

### Reject / Weak

`brewlens`

- Already used by a Homebrew app/store-style project.
- Avoid.

`tapq`

- Too tap-specific; this tool queries packages, not just taps.

`kegq`

- Available-looking but too inside-baseball and hard to read.

`cellarq`

- Available-looking but obscure and long.

`brewlist`

- Too narrow; only covers installed-list behavior.

`brewpeek`

- Cute but less clear than `brewq` or `brewfind`.

## MVP Recommendation

Build `brewq` / `bsx` as:

1. cache-backed name search
2. cache-backed description search
3. installed package list
4. configurable columns
5. table + JSON output
6. cache status/refresh/clear

Do not build package mutation or interactive browsing.

## Implementation Notes

- Pre-index analytics by package name during cache build. The zsh prototype does repeated linear scans in `jq`; this will become a performance drag.
- Prefer one merged search index file plus raw/source cache files for debugging.
- Keep list analytics cache-only by default; avoid per-package network calls in `list`.
- Preserve formula-before-cask grouping for `list` unless config says otherwise.
- Remove duplicated shell cache-build functions from dotfiles after the standalone tool replaces them.

## Sources

- Homebrew Querying Brew: https://docs.brew.sh/Querying-Brew
- Homebrew Analytics: https://docs.brew.sh/Analytics
- Homebrew Formulae API: https://formulae.brew.sh/docs/api/
- formulae.brew.sh Analytics: https://formulae.brew.sh/analytics/
- brew-discover article: https://zenn.dev/atani/articles/brew-discover-cli-tool?locale=en
- Brewse PyPI: https://pypi.org/project/brewse/
- fex docs.rs: https://docs.rs/crate/fex/0.5.0
- Bold Brew: https://bold-brew.com/
- Tappie: https://www.empiricapps.com/tappie
- BrewLens: https://amit9838.github.io/brewlens/
