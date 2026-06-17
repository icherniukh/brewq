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
- use install counts as a trust/quality signal
- show useful configurable columns
- provide script-friendly output
- list installed formulae/casks with richer metadata
- keep cache behavior visible and reliable

Avoid over-locking undecided details. If a choice is not settled, mark it as `deferred` or `open` instead of turning it into implementation policy.

## Current CLI Contract

The current implementation and docs intentionally settle these first-release choices:

- Search is the root command: `brewq [search-options] <query...>`.
- Default search matches package names, formula aliases, and descriptions.
- Search defaults to 30-day install analytics ranking.
- `-s` / `--sort` selects `30d`, `90d`, `365d`, or `name`.
- `-t` / `--top` is the search result cap for top-ranked matches.
- `list --limit` is the installed-list cap.
- `-p` selects built-in presets; `-c` selects explicit comma-joined columns.
- `--tsv` is the only public machine-readable output mode.
- `list --analytics` merges cached analytics; `list --fetch` may refresh before rendering.
- `random` is a local layout lab command. It is not a product-level random browser.

## Working Rules

- Read the relevant docs before changing code.
- Preserve `legacy/bsx-prototype.zsh` as provenance until replacement behavior is implemented and verified.
- Keep competitor discussion isolated to private/internal docs; do not copy it into public README/release copy.
- Prefer small, reviewable changes.
- Verify factual claims against files or commands.
- Do not push or otherwise touch remotes unless explicitly asked.

## Remaining Open Decisions

Treat these as open until a later spec resolves them:

- Cache matching strategy: whether normal search shells out to `brew search` for matching or searches directly in a local cache/index.
- Cache refresh defaults: manual, stale-while-revalidate, blocking-when-missing, live fallback, or a measured hybrid.
- Cold-cache behavior: how long first run may wait before falling back to live Homebrew data.
- Grouping behavior: whether formulae and casks are mixed by relevance by default, with grouping deferred or exposed.
- Status behavior: how deprecated and disabled packages affect display and ranking.
- First release packaging: Python-only release versus including the zsh prototype as unsupported legacy.
- Post-replacement cleanup: when to update dotfiles, remove/archive `dot_scripts/executable_bsx`, and replace the old ccconfig guide with a pointer here.
- Deferred query features: trend score, semantic/vector search, `info`, `--exact`, `--explain`, `--open`, and `list --leaves`.
- Future rewrite: whether Rust/Go is justified after measuring Python bottlenecks.

## Tracker

Use local beads for project status:

- `bd ready`
- `bd list --status=in_progress`

Transferred tracker item:

- `brewq-d9n`: `Implement brewq Python CLI from transferred bsx scope`
