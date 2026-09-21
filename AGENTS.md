# AGENTS.md

This repo is the new home for `brewq`: a read-only Homebrew query and analytics tool.

## Orientation

- Canonical vision: `docs/vision.md`
- Directional product spec: `docs/product-spec.md`
- CLI sketch: `docs/cli-design.md`
- Local workflows to replace: `docs/local-workflows.md`
- Historical prototype: `legacy/bsx-prototype.zsh`

`brewq` is not a Homebrew manager. Do not add install, uninstall, upgrade, services, Brewfile, TUI, GUI, or multi-package-manager behavior unless the product direction is explicitly changed.

## Current Framing

The core shape is query + analytics:

- query packages by name and description
- surface raw 90-day install volume as the default trust/discovery signal —
  see brewq-253; a trending signal (recent install rate vs. a package's own
  historical baseline) remains available as an explicit, demoted metric
- show useful configurable columns
- provide script-friendly output
- list installed formulae/casks with richer metadata
- keep cache behavior visible and reliable

Avoid over-locking undecided details. If a choice is not settled, mark it as `deferred` or `open` instead of turning it into implementation policy.

## Current CLI Contract

The current implementation and docs intentionally settle these first-release choices:

- Search is the root command: `brewq [search-options] <query...>`.
- Packaging ships two identical console-script entry points, `brewq` and `bq`
  (both `= "brewq.cli:main"` in `pyproject.toml`), so a short name is available
  out of the box without requiring `brew alias` setup — the same pattern
  ripgrep uses for `rg`.
- Default search matches package names, formula aliases, and descriptions.
- Search defaults to raw 90-day install volume ranking — see brewq-253. Reversed
  from an earlier trending-by-default direction (see brewq-4it/brewq-sbe)
  because a self-relative growth ratio lets low-volume "new package" artifacts
  (recently added to Homebrew analytics tracking, not genuinely adopted)
  outrank widely-used packages. The default table shows a literal
  `installs_90d` column alongside `TREND`, not the old `auto` picked-window
  column.
- `Package.trending` returns a recent installation rate, anchored on the 90d
  window (`installs_90d / 3`, a several-week smoothed rate) rather than the
  raw 30d snapshot, as a multiplier of a span-weighted baseline from the
  365d window (`4.1x`, `1.0x` = unchanged), using pseudocount smoothing
  (`_TREND_PSEUDOCOUNT`, calibrated at 30) rather than a post-hoc confidence
  discount + hard clamp — see brewq-sbe. The pseudocount also scales up to 3x
  (`_TREND_MATURITY_BOOST`) when a package has few installs recorded before
  its most recent 90d window, tapering to 1x by `_TREND_MATURITY_THRESHOLD`
  (1500) — see brewq-4o0 (bun/sdl2-compat-style tracking artifacts otherwise
  read as 150-270x). There is no ceiling; low-volume noise and thin history
  are both damped by the pseudocount, not clamped. It remains available as an
  explicit, demoted sort/column.
- `-s` / `--sort` selects `90d` (default), `30d`, `365d`, `trending`, or `name`.
  `auto` remains a config-only pseudo-column (not selectable via `-s`/`-c`) for
  a user's own `output.columns` list, resolving to whichever of
  90d/30d/365d has data for the top-ranked result.
- Search caps results adaptively: `-t` / `--top` wins, then `output.limit`
  from config when > 0, then terminal height on a TTY (`rows - 6`, minimum 5),
  then no cap when piped. There is no fixed top-N constant.
- `list --limit` is the installed-list cap.
- `-c` selects explicit comma-joined columns. No named presets: `-u` adds the
  `url` column to the active set, `-v` shows all package fields. `-c` and `-v`
  are mutually exclusive.
- Deprecated/disabled packages are hidden when results would overflow the cap;
  `--all` includes them. Uncapped (piped) output keeps them but ranks them
  after active packages.
- Formula/cask name colors use theme-relative standard 16-color ANSI codes
  (cyan/magenta) so they follow the terminal theme; color is TTY-only and
  honors `NO_COLOR`.
- `--tsv` is the only public machine-readable output mode.
- Releases bundle a seed cache so the first query does not block on a full refresh.
- When the seed is used, brewq overlays installed state from the local Cellar/Caskroom before rendering.
- Fresh cache paths are cache-only. Stale cache renders immediately and schedules one detached, delayed, low-load refresh.
- `refresh` and `-r` remain optional foreground recovery controls, not setup requirements.
- `list --analytics` exposes analytics already present in the cache.
- `random` is a local layout lab command. It is not a product-level random browser.

## Verification

Run before opening a PR:

```
uv run python scripts/verify.py
```

This chains `ruff check`, `pytest`, functional CLI smoke checks (search/list, table/TSV,
non-TTY ANSI-leak check), and the installed `brewq` shim if one is on `PATH`. It is the
project's real pre-PR gate — `bd preflight`'s built-in checklist targets Go projects
(`go test`, `golangci-lint`, `gofmt`) and does not apply to this repo; ignore it.

Individual commands, for iterating on one area:

- `uv run ruff check .` — lint
- `uv run pytest -q` — unit tests (analytics, cache, cli, columns, config, inventory,
  model, options, render, scheduler, seed)
- `uv run python scripts/verify.py` — full gate, including subprocess-level CLI checks
  the unit tests don't cover

## Working Rules

- Read the relevant docs before changing code.
- Preserve `legacy/bsx-prototype.zsh` as provenance until replacement behavior is implemented and verified.
- Keep competitor discussion isolated to private/internal docs; do not copy it into public README/release copy.
- Prefer small, reviewable changes.
- Verify factual claims against files or commands.
- Do not push or otherwise touch remotes unless explicitly asked.

## Remaining Open Decisions

Treat these as open until a later spec resolves them:

- Grouping behavior: whether formulae and casks are mixed by relevance by default, with grouping deferred or exposed.
- Status filtering: deprecated/disabled packages are hidden from capped results
  (`--all` shows them) and demoted to the end of uncapped output; whether exact
  matches should still surface them is open.
- First release packaging: Python-only release versus including the zsh prototype as unsupported legacy.
- Post-replacement cleanup: when to update dotfiles, remove/archive `dot_scripts/executable_bsx`, and replace the old ccconfig guide with a pointer here.
- Deferred query features: semantic/vector search, `info`, `--exact`, `--explain`, `--open`, and `list --leaves`.
  (Trend score shipped as the default `trending` sort/column; no longer deferred.)
- Future rewrite: whether Rust/Go is justified after measuring Python bottlenecks.

## Tracker

Use local beads for project status:

- `bd ready`
- `bd list --status=in_progress`

Transferred tracker item:

- `brewq-d9n`: `Implement brewq Python CLI from transferred bsx scope`
