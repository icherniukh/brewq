# Product Spec

This spec is intentionally directional. It defines the product boundaries and core interfaces, but avoids over-prescribing ranking formulas, renderer details, cache internals, or implementation order. Future implementation work should inspect the code, Homebrew behavior, and real output before filling in specifics.

## Product

`brewq` is a read-only Homebrew query tool.

It helps answer:

- What package matches this name, description, or capability?
- Which matching packages look more trustworthy based on install analytics?
- What useful metadata should I see before deciding?
- What Homebrew packages do I already have installed?

It should stay close to Homebrew query workflows and avoid becoming a package manager.

## Core Workflows

### Search / Query

Default query should be useful for product discovery and analytics-backed comparison:

```bash
brewq ripgrep
brewq --desc terminal multiplexer
brewq --top 10 json
```

Expected behavior:

- Search package names and cask tokens by default, matching Homebrew's default search scope.
- Keep `--desc` as the explicit name+description discovery mode.
- Rank with install analytics as a major signal.
- Mark installed, deprecated, and disabled packages when known.
- Support formula/cask filtering.

Do not hardcode a final scoring formula in this spec. Ranking should be implemented in a way that can be tuned after real output review.

### Installed List

`brewq list` should replace the useful parts of the current `brew_installed` / `brew-ll` shell workflow:

```bash
brewq list
brewq list --analytics
brewq list --columns compact
brewq list --json
```

Expected behavior:

- Show installed formulae and casks together.
- Use the same record/column/output model as query results.
- Avoid network fetches by default.
- Make analytics optional and cache-backed.

### Cache

Cache should be visible enough to trust:

```bash
brewq cache status
brewq cache refresh
brewq cache clear
```

Expected behavior:

- Warm-cache queries should be fast.
- Normal query should not require network access.
- Refresh should be atomic and lock-protected.
- Missing/stale cache behavior can be tuned; do not over-design it before measurement.

## Output

Output should be compact by default and customizable without flag sprawl.

Use columns as the primary extension mechanism:

```bash
brewq --columns compact rust
brewq --columns full rust
brewq --columns name,type,installs,url rust
```

First-class output forms:

- table for humans
- JSON for scripts

Column presets should exist, but exact preset definitions may evolve:

- `compact`
- `default`
- `full`

Defaults should come from config when present, with useful built-in defaults when absent.

## Config

Config should control defaults, not become an application framework.

Likely config path:

```text
${XDG_CONFIG_HOME:-~/.config}/brewq/config.toml
```

Likely config areas:

- default columns
- default metric
- default output format
- default cache behavior
- default row/top count

Avoid config editing commands in the first release. `brewq config path` is enough if path discoverability is needed.

## Analytics

Install analytics are a core part of the product, not decoration.

Initial useful metrics:

- 30-day installs
- 365-day installs

Possible later metrics:

- 90-day installs
- trend score
- popularity buckets

Trend score is explicitly undecided. It should be explored after the first useful version exists.

## Brew Alias Support

The tool should work standalone and be easy to expose through Homebrew aliases.

Possible alias layer:

```bash
brew alias "q=!brewq"
brew alias "qd=!brewq --desc"
brew alias "ql=!brewq list"
```

Aliases are convenience wrappers. They should not force `brewq` to become a wrapper for all `brew` interactions.

## Out Of Scope

Do not build these into the core product:

- install/uninstall/upgrade
- services management
- Brewfile management
- cleanup workflows
- TUI/GUI
- multi-package-manager abstraction
- remote sync
- security scanner

## Future Directions

These are plausible but not first-release requirements:

- semantic/vector search over descriptions and project pages
- cache strategy profiles
- `info NAME`
- `list --leaves`
- `--exact`
- `--explain`
- `--open`
- extremely optimized Rust/Go rewrite after measuring real bottlenecks

## Success Criteria

- `brewq QUERY` helps compare package options faster than plain `brew search`.
- install counts are visible enough to support trust/quality judgment.
- `brewq --top N QUERY` is useful for finding the most credible candidates.
- `brewq list` replaces the existing installed-package function.
- output presets are useful, but custom columns are still easy.
- JSON output is stable enough for scripts.
- first release remains compact and read-only.
