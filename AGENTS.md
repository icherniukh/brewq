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

## Working Rules

- Read the relevant docs before changing code.
- Preserve `legacy/bsx-prototype.zsh` as provenance until replacement behavior is implemented and verified.
- Keep competitor discussion isolated to private/internal docs; do not copy it into public README/release copy.
- Prefer small, reviewable changes.
- Verify factual claims against files or commands.
- Do not push or otherwise touch remotes unless explicitly asked.

## Open Decisions

Treat these as open until a later spec resolves them:

- Default search semantics: name-only by default versus name + description by default.
- Description flags: whether `--desc` means include descriptions, whether `--desc-only` exists, and whether `--name-only` is the compatibility mode.
- Result cap semantics: whether `--top N` is distinct from `--limit N`, and what each guarantees.
- Column presets: exact columns for `compact`, `default`, `full`, and installed-list views.
- Analytics metric defaults: whether 30-day installs remain default and 365-day installs stay behind `-y` / `--year`.
- Cache matching strategy: whether normal search shells out to `brew search` for matching or searches directly in a local cache/index.
- Cache refresh defaults: manual, stale-while-revalidate, blocking-when-missing, live fallback, or a measured hybrid.
- Cold-cache behavior: how long first run may wait before falling back to live Homebrew data.
- Grouping behavior: whether formulae and casks are mixed by relevance by default, with grouping deferred or exposed.
- Status behavior: how deprecated and disabled packages affect display and ranking.
- List analytics behavior: cache-only by default versus optional per-package fetch with `--fetch`.
- First release packaging: Python-only release versus including the zsh prototype as unsupported legacy.
- Post-replacement cleanup: when to update dotfiles, remove/archive `dot_scripts/executable_bsx`, and replace the old ccconfig guide with a pointer here.
- Deferred discovery features: trend score, semantic/vector search, `info`, `--exact`, `--explain`, `--open`, and `list --leaves`.
- Future rewrite: whether Rust/Go is justified after measuring Python bottlenecks.

## Tracker

Use local beads for project status:

- `bd ready`
- `bd list --status=in_progress`

Transferred tracker item:

- `brewq-d9n`: `Implement brewq Python CLI from transferred bsx scope`
