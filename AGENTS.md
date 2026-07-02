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
- surface a trending signal (recent install rate vs. a package's own historical
  baseline) as the default trust/discovery signal; raw install counts remain
  available as an explicit, opt-in metric
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
- Search defaults to trending ranking: `Package.trending` returns the most recent
  30-day install rate as a multiplier of a span-weighted baseline from the
  90d/365d windows (`4.1x`, `1.0x` = unchanged), using pseudocount smoothing
  (`_TREND_PSEUDOCOUNT`, calibrated at 20) rather than a post-hoc confidence
  discount + hard clamp — see brewq-sbe. There is no ceiling; low-volume noise
  is damped by the pseudocount itself. The default table also shows one raw
  install-count column (`auto`, picked from whichever of 30d/90d/365d has data
  for the top result) alongside `TREND`.
- `-s` / `--sort` selects `trending` (default), `30d`, `90d`, `365d`, or `name`.
  Raw install counts stay fully available via `-s 30d`/`-c 30d` etc.; they are no
  longer the default public ranking signal.
- Search defaults to the top 15 matches; `-t` / `--top` overrides the cap.
- `list --limit` is the installed-list cap.
- `-p` selects built-in presets; `-c` selects explicit comma-joined columns.
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
- Status filtering: whether deprecated and disabled packages are hidden by default,
  and whether exact matches or an explicit override still show them.
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
