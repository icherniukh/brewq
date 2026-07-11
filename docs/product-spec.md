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
brewq terminal multiplexer
brewq -t 10 json
brewq -s 365d rust
```

Expected behavior:

- Search package names, formula aliases, and descriptions by default.
- Rank with install analytics as a major signal.
- Mark installed, deprecated, and disabled packages when known.
- Support an installed-only filter.

Do not hardcode a final scoring formula in this spec. Ranking should be implemented in a way that can be tuned after real output review.

### Installed List

`brewq list` should replace the useful parts of the current `brew_installed` / `brew-ll` shell workflow:

```bash
brewq list
brewq list --analytics
brewq list -p compact
brewq list --tsv
```

Expected behavior:

- Show installed formulae and casks together.
- Use the same record/column/output model as query results.
- Avoid network fetches by default.
- Make analytics optional and cache-backed.
- Default installed columns should include `type`, because list output mixes formulae and casks.

### Cache

Cache should be visible enough to trust:

```bash
brewq refresh
brewq -r ripgrep
```

Expected behavior:

- Warm-cache queries should be fast.
- Normal query should not require network access.
- Refresh should be atomic and lock-protected.
- Normal search/list should disclose cache age concisely.
- Releases should include a seed cache so first use does not block on refresh.
- Seed-backed first use should overlay installed state from local Homebrew storage.
- Stale cache should render immediately, then schedule one delayed low-load refresh.
- Manual refresh should remain optional recovery and diagnostics behavior.

## Output

Output should be compact by default and customizable without flag sprawl.

Use columns as the primary extension mechanism:

```bash
brewq -p compact rust
brewq -p full rust
brewq -c name,type,30d,url rust
```

First-class output forms:

- table for humans
- raw TSV for scripts

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
- default sort
- default cache behavior
- default row/top count

Avoid config editing commands in the first release. `brewq config path` is enough if path discoverability is needed.

## Analytics

Install analytics are a core part of the product, not decoration.

Initial useful metrics:

- 30-day installs
- 90-day installs
- 365-day installs

Raw 90-day install volume (`installs_90d`) is the default public ranking/column
signal — see brewq-253. `trending` (a 90d-anchored installation rate as a
multiplier of a span-weighted 365d baseline, e.g. `4.1x`) remains available as
an explicit, demoted sort/column, alongside the other raw install-count
windows.

Superseded: `trending` was briefly the default ranking/column signal — see
brewq-4it. A composite "popularity buckets" score was considered and rejected
in favor of it at the time: an opaque 0-100 blend was harder to justify than a
directly interpretable recent-vs-history multiplier. That default changed back
— see brewq-253 — because a self-relative growth ratio rewards packages that
are merely new to analytics tracking (a handful of installs can read as a
~250x multiplier) over packages with a large, trustworthy install base, which
is the opposite of what a default sort should optimize for.

The multiplier uses pseudocount smoothing (add a fixed count to both the recent
and baseline rate before dividing) rather than a post-hoc confidence discount
plus hard clamp — see brewq-sbe. The earlier clamp-based version tied dozens of
unrelated packages at an identical `+300%` ceiling and hid packages with zero
measurable history entirely; the same instability that RNA-seq differential
expression tools (DESeq2/apeglm) solve with fold-change shrinkage for low-count
genes, applied here to low-volume packages.

Superseded: even with pseudocount smoothing, packages new to Homebrew analytics
tracking (near-zero installs recorded before their most recent 90d window)
still read as huge, misleading spikes — e.g. bun at 156-271x, sdl2-compat at
271x on a single pre-90d install — see brewq-4o0. Two changes fixed this
without reintroducing a hard clamp: the "recent" rate is now anchored on the
90d window (`installs_90d / 3`, a several-week smoothed rate) instead of the
raw 30d snapshot, which dampens any burst concentrated entirely in the last 30
days regardless of whether the package is new or established; and the
pseudocount itself scales up (to 3x at zero pre-90d installs, tapering back to
1x by 1,500 pre-90d installs) rather than staying fixed, so packages with thin
history are pulled toward neutral in proportion to how thin it is, not
collapsed flat to 1.0x. Calibrated interactively against live cache data.

## Brew Alias Support

The tool should work standalone and be easy to expose through Homebrew aliases.

Possible alias layer:

```bash
brew alias "q=!brewq"
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

`brewq random` is allowed as a local lab command for exercising layouts and finding inspiration during development. It should stay small and route through normal search/output code. It is not a commitment to product-level random discovery or category browsing.

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
- `brewq -t N QUERY` is useful for finding the most credible candidates.
- `brewq list` replaces the existing installed-package function.
- output presets are useful, but custom columns are still easy.
- TSV output is stable enough for scripts.
- first release remains compact and read-only.
